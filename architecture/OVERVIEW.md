# Architecture

## Overview

MCP Hangar is the **Kubernetes-native policy enforcement plane for MCP**. Every
tool call an agent makes runs through one deterministic allow/deny path before it
reaches an upstream MCP server. Enforcement is rule-based and deterministic —
there are no anomaly scores and no baseline to train. MCP Hangar is MIT-licensed
and self-hosted; there is no SaaS, managed, or enterprise tier.

Enforcement is delivered across **two distinct planes**:

- **The per-request enforcement plane** (core, `mcp-hangar` on PyPI) — an ordered
  pipeline of controls that fires on every synchronous `tools/call`, ending with
  an L7 egress-policy gate immediately before the wire.
- **The deploy-time admission plane** (the operator, `mcp-hangar-operator`) —
  Kubernetes admission webhooks and network policy that decide, at pod/CR
  admission time, whether a workload may exist and where it may talk. This is a
  *different plane and a different temporal moment* from the per-request path.

A third capability — a **governed async task relay with a mid-flight consent
gate** — is landing in 2.0 (v2 preview; see below).

Beyond enforcement, MCP Hangar also manages MCP servers with explicit lifecycle,
health monitoring, and automatic cleanup — the machinery the enforcement path
runs on top of.

MCP Hangar is organized as a monorepo plus the operator:

| Package | Description | Location |
|---------|-------------|----------|
| **Core package** | Python library (PyPI: `mcp-hangar`) — enforcement pipeline, auth, compliance, approvals, integrations, persistence | `src/mcp_hangar/` |
| **Operator** | Kubernetes operator (Go) — admission webhooks, CRDs, network policy, MCPEgressPolicy controller | `mcp-hangar-operator` (separate repo) |

Since v1.3.0, the core is a single MIT-licensed package. The former `enterprise/`
package was absorbed into `src/mcp_hangar/`; features are no longer split by
license tier or gated by license keys.

**Key concepts:**

- **Enforcement pipeline** -- Ordered per-request controls on every tool call
- **Admission plane** -- Deploy-time pod registration, image-digest pinning, default-deny egress ([ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md))
- **Egress L7 policy** -- Tool/argument-level allow/deny, the last gate before upstream
- **MCP servers** -- Subprocesses or containers exposing tools via JSON-RPC
- **State machine** -- COLD -> INITIALIZING -> READY -> DEGRADED -> DEAD
- **Health monitoring** -- Failure detection with circuit breaker
- **GC** -- Automatic shutdown of idle MCP servers
- **CQRS / Event Sourcing** -- Command/query separation; append-only event store ([Event Sourcing](EVENT_SOURCING.md))
- **Digest Pinning** -- SHA-256 tool-schema verification ([ADR-004](../adr/ADR-004-sep-1766-digest-pinning.md))
- **Interceptor Framework** -- Experimental pre/post hooks, off by default ([ADR-005](../adr/ADR-005-sep-1763-interceptor-compliance.md))

## The per-request enforcement pipeline (core, v1.6.0)

Every governed synchronous `tools/call` funnels through a single chokepoint (the
batch executor; the front-door flat `tools/call` handler delegates to it to reuse
the exact same path). The controls fire in a **definite order** — this is a
pipeline, not a flat seam — and the egress L7 gate sits at the very end, inside
tool invocation, just before any bytes leave for the upstream:

| # | Control | Notes | Status |
|---|---------|-------|--------|
| 1 | **Identity / auth middleware** | Authenticates the request and binds the tenant (ASGI middleware, upstream of the pipeline) | v1.6.0 |
| 2 | **Tool-access authz** | Tenant/member scope check — is this caller allowed this tool? | v1.6.0 |
| 3 | **Tool-withdrawal check** | Per-tenant withdrawal of a previously exposed tool | v1.6.0 |
| 4 | **Tool-schema digest-pin verify** | SHA-256 pin over the tool's canonical schema; audit/warn/block, fails closed under block | v1.6.0 (opt-in) |
| 5 | **Circuit-breaker / health** | Rejects calls to unhealthy servers/groups | v1.6.0 |
| 6 | **Interceptor validators** | Empty/no-op unless explicitly configured | v1.6.0 (experimental, **off by default**) |
| 7 | **Approval gate (HITL)** | If approval is required, the call **fails closed** (it is blocked, not queued for an interactive prompt) | v1.6.0 |
| 8 | **Concurrency / backpressure** | Global + per-server semaphores | v1.6.0 |
| 9 | **Interceptor mutators (request)** | Argument rewriting; no-op unless configured | v1.6.0 (experimental, off) |
| 10 | **Egress L7 policy** | **The last gate before the wire.** Tool-name globs + secret-pattern + payload-size scan; DENY or REQUIRE_APPROVAL. Evaluated inside tool invocation, before cold-start and before any upstream I/O | v1.6.0 |
| → | **Upstream MCP server** | Hangar-originated connection | |
| 11 | **Interceptor mutators (response)** + **response truncation** | Response-side transforms; oversized responses truncated | v1.6.0 |

**Cross-cutting: audit & observability.** Every governed step emits both **domain
events** (on the event bus, persisted to the event store) and **OTel spans**
(`policy.check_access`, `approval_gate.check`, `concurrency.acquire`,
`command.send.InvokeToolCommand`, and the per-tool call span). Telemetry follows
the OTel GenAI/MCP semantic conventions (`gen_ai.tool.name`, `mcp.method.name`,
`gen_ai.operation.name`). See [Observability](../guides/OBSERVABILITY.md).

Notes and honest caveats:

- **Interceptors are experimental and off by default.** The validator/mutator
  pipelines register no interceptors out of the box; the public
  `interceptors/list` endpoints are conformance-shaped no-ops. Do not treat
  interceptors as a live enforcement control. See
  [Interceptor Framework](INTERCEPTOR_FRAMEWORK.md).
- **The sync L7 `requireApproval` outcome fails closed** — it blocks the call. It
  is not an interactive approval queue or a human prompt-and-wait. The only
  genuinely interactive consent flow is the v2 relay consent gate (below).
- Deeper detail: [Front-Door Mode & Per-Tenant Tool Governance](../guides/FRONT_DOOR.md),
  [Egress Policy](../guides/EGRESS_POLICY.md), [Authentication & RBAC](../guides/AUTHENTICATION.md).

## The deploy-time admission plane (operator)

The operator enforces at Kubernetes pod/CR admission — a **separate plane** from
the per-request pipeline. It applies only in namespaces labeled
`mcp-hangar.io/enforce-egress=true` (opt-in, governed namespaces). The CRD API
version is `v1alpha2`. See [ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md).

- **Pod-registration webhook** — denies a pod that claims to be an MCP server
  unless a registered `MCPServer` CR exists (validating, fail-closed).
- **CR validation** — validates `MCPServer` / policy custom resources on
  create/update.
- **Image-digest pinning** — requires `image@sha256:...`; modes off/warn/block.
  (Distinct from the request-path *tool-schema* digest pin — different digest,
  different plane.)
- **Default-deny egress + L3/L4 network backstop** — restricts which hosts a
  server pod may reach. FQDN upstreams require the Cilium flavor.
- **MCPEgressPolicy controller** — compiles an `MCPEgressPolicy` CR and pushes the
  L7 policy down to the core engine, where it is enforced at the tool-invocation
  chokepoint (control #10 above).

**End-to-end L7 egress enforcement is available today** with core engine v1.6.0 +
operator **v0.14.0** (released 2026-07-19, the latest operator release), which
ships the MCPEgressPolicy controller. The core L7 engine and REST intake are armed
in v1.6.0; the operator now delivers policies to it end-to-end.

Current chart versions: `mcp-hangar` 0.13.4 (appVersion 1.6.0),
`mcp-hangar-operator` 0.12.3 (appVersion 0.14.0).

## v2 preview: governed async task relay + consent (landing in 2.0)

A governed async-task capability is **landing in 2.0** and ships today only as a
prerelease (`pip install --pre mcp-hangar`); stable installs still land on 1.6.0.
See [ADR-014](../adr/ADR-014-tasks-relay-with-governance.md) and
[Governed Tasks](../guides/GOVERNED_TASKS.md).

- **Relay with governance, not an executor.** Hangar never creates or runs tasks;
  it captures an upstream-returned task handle and governs it. There is no
  scheduler, job runner, or result store. Every relayed task is governed at relay
  time (`GovernedTaskStore` + a `TaskCreated` audit event). This supersedes the
  earlier relay-only stance ([ADR-008](../adr/ADR-008-tasks-relay-only.md)) in part.
- **Serving handlers**: `tasks/get`, `tasks/result` (with pinned-digest
  re-verification), `tasks/cancel`, and owner-only `tasks/list`.
- **Mid-flight consent gate** — on an upstream `input_required`, the call is
  routed to genuinely interactive HITL elicitation and **fails closed** absent
  consent. This is the *only* interactive consent flow in the system (contrast the
  sync L7 `requireApproval`, which merely blocks).
- Gated by the `relay_tasks_enabled` kill-switch. The 2026-07-28 SEP-2663 Tasks
  reshape is forward-compat-guarded, not live behavior.

Public version surfaces remain 1.6.0; everything in this section is labeled
"landing in 2.0" and is not implied as shipped in the stable release.

## Layer Structure (DDD + CQRS)

The Python core follows Domain-Driven Design with strict layer separation:

```
src/mcp_hangar/
+-- domain/           Core business logic (NO external dependencies)
|   +-- model/        Aggregates: MCP Server, McpServerGroup
|   +-- events.py     Domain events
|   +-- exceptions.py Exception hierarchy
|   +-- value_objects/ McpServerId, McpServerMode, IdleTTL, ToolDigest, etc.
|   +-- policies/     Egress L7 policy engine (deterministic evaluate())
|   +-- services/     Digest validator, tool-access resolver, task consent
|   +-- contracts/    Interfaces (IMetricsPublisher, IMcpServerRuntime)
|   +-- security/     Rate limiting, input validation
|
+-- application/      Use cases and orchestration
|   +-- commands/     Command handlers (CQRS write side)
|   +-- queries/      Query handlers (CQRS read side)
|   +-- sagas/        Long-running processes (recovery, failover)
|   +-- event_handlers/ React to domain events
|   +-- services/     Application services (TracedMcpServerService)
|   +-- ports/        Port interfaces (ObservabilityPort)
|
+-- infrastructure/   External concerns (implements domain contracts)
|   +-- discovery/    Docker, K8s, filesystem, entrypoint sources
|   +-- identity/     Identity middleware (tenant binding)
|   +-- persistence/  Repositories, Event Store (SQLite, in-memory)
|   +-- registry/     Registry client
|   +-- event_bus.py  In-process event bus
|   +-- command_bus.py CQRS command dispatcher
|   +-- query_bus.py  CQRS query dispatcher
|
+-- server/           Protocol and transport layer
    +-- api/          REST API (Starlette routes)
    |   +-- ws/       WebSocket endpoint (events)
    +-- tools/        MCP tool implementations + batch executor (the chokepoint)
    +-- bootstrap/    DI composition root
    +-- cli/          CLI (typer-based)
```

**Layer dependencies flow inward only:** Domain knows nothing about
infrastructure. Infrastructure implements domain contracts. Server depends on all
layers.

## System Architecture

```
+------------------------------------------------------------------+
|                    REST API (Starlette)                           |
|   /api/mcp_servers  /api/groups  /api/discovery  /api/ws/*         |
+----------------------------------+-------------------------------+
                                   |
+----------------------------------v-------------------------------+
|                    MCP Protocol Layer                             |
|             FastMCP server (stdio or HTTP transport)              |
|         hangar_* MCP tools  |  tools/call enforcement chokepoint  |
+----------------------------------+-------------------------------+
                                   |
+----------------------------------v-------------------------------+
|                    CQRS + Event Bus                               |
|   CommandBus -> Handlers   QueryBus -> Handlers   EventBus       |
+--------+-----------+-------------+-------------------------------+
         |           |             |
+--------v--+ +------v------+ +---v----+
|  MCP Server  | | McpServerGroup| |  Sagas  |
| Aggregate  | |  Aggregate   | |         |
+--------+---+ +------+------+ +---------+
         |           |
+--------v-----------v--------------------------------------------+
|                    Infrastructure                                |
|  StdioClient | DockerLauncher | EventStore | HealthTracker       |
|  Discovery Sources | Registry Client | Log Buffers               |
+------------------------------------------------------------------+
```

## State Machine

```
     COLD
       | ensure_ready()
       v
  INITIALIZING
       |
       +-> SUCCESS --> READY
       |                 | failures >= threshold
       |                 v
       |              DEGRADED
       |                 | reinitialize
       |                 +-> INITIALIZING
       |
       +-> FAILURE --> DEAD
                         | retry < max
                         +-> INITIALIZING
```

**Valid transitions:**

| From | To |
|------|----|
| COLD | INITIALIZING |
| INITIALIZING | READY, DEAD, DEGRADED |
| READY | COLD, DEAD, DEGRADED |
| DEGRADED | INITIALIZING, COLD |
| DEAD | INITIALIZING, DEGRADED |

There is no direct DEGRADED -> READY transition. Degraded MCP servers must
reinitialize.

## CQRS Pattern

Commands modify state, queries read state. They never mix.

- **Commands**: `StartMcpServerCommand`, `CreateMcpServerCommand`, `CreateGroupCommand`, `SetEgressPolicyCommand`, etc.
- **Queries**: `ListMcpServersQuery`, `GetMcpServerQuery`, `GetSystemMetricsQuery`, etc.
- **Events**: `McpServerStarted`, `ToolInvocationCompleted`, `HealthCheckFailed`, `DigestMismatchEvent`, etc.

All state changes emit domain events via `AggregateRoot._record_event()`. Events
are persisted to the Event Store for auditing and can be replayed. See
[Event Sourcing](EVENT_SOURCING.md).

## Threading

### Lock Hierarchy

Acquire in order to avoid deadlocks (see `infrastructure/lock_hierarchy.py`):

```
PROVIDER(10) < PROVIDER_GROUP(11) < EVENT_BUS(20) < EVENT_STORE(30) < SAGA_MANAGER(40) < STDIO_CLIENT(50)
```

`TrackedLock` enforces this ordering at runtime.

### Threads

| Thread | Purpose |
|--------|---------|
| Main | FastMCP server, tool calls |
| Reader (per MCP server) | Read stdout, dispatch responses |
| Stderr Reader (per MCP server) | Capture stderr into log buffer |
| GC Worker | Idle MCP server cleanup |
| Health Worker | Periodic health checks |
| Metrics Snapshot Worker | Periodic metrics history capture |

### Safe I/O Pattern

```python
# Copy reference under lock, I/O outside lock
with lock:
    if state == READY:
        client = conn.client
response = client.call(...)  # Outside lock
```

## Error Handling

| Category | Strategy |
|----------|----------|
| Transient (timeout) | Retry with backoff |
| Permanent (not found) | Fail fast, mark DEAD |
| MCP Server (app error) | Propagate, track metrics |

### Circuit Breaker

MCP Server groups use a circuit breaker to isolate failing members:

- **CLOSED** -- Normal operation, failures tracked
- **OPEN** -- Requests rejected, backoff timer active
- **HALF_OPEN** -- Single test request allowed to probe recovery

## Performance

**Recommended TTL:**

- Subprocess: 180-300s
- Container: 300-600s
- Remote: 600+ (connection pooling)
