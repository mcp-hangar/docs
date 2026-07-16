# Architecture Decision Records

This directory contains the Architecture Decision Records (ADRs) for MCP
Hangar. Each ADR captures a single architectural decision -- the context
that led to it, what was decided, and the consequences. ADRs are immutable
once accepted; changing a decision requires a new ADR that supersedes the
old one. See [ADR_AGENTS.md](https://github.com/mcp-hangar/mcp-hangar/blob/main/docs/internal/ADR_AGENTS.md) for the full governance rules, status
taxonomy, and formatting conventions.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](ADR-001-cqrs.md) | Command Query Responsibility Segregation (CQRS) | Accepted | 2026-04-17 |
| [002](ADR-002-event-sourcing.md) | Event Sourcing | Accepted | 2026-04-17 |
| [003](ADR-003-sagas.md) | Saga Pattern | Accepted | 2026-04-17 |
| [004](ADR-004-sep-1766-digest-pinning.md) | Preemptive Implementation of SEP-1766 (Digest Pinning) and SEP-1763 (Interceptor Framework) | Accepted | 2026-05-01 |
| [005](ADR-005-sep-1763-interceptor-compliance.md) | SEP-1763 Interceptor Framework Compliance | Accepted | 2026-05-01 |
| [006](ADR-006-tetragon.md) | Runtime Enforcement Strategy -- Tetragon-First, Pluggable Backend | Accepted | 2026-05-10 |
| [007](ADR-007-langfuse-integration.md) | Langfuse Integration for LLM Observability | Accepted | 2026-01-12 |
| [008](ADR-008-tasks-relay-only.md) | Task Governance is Relay-Only -- Hangar is a Task Relay, Not a Task Executor | Accepted | 2026-07-02 |
| [009](ADR-009-independent-release-topology.md) | Independent Release Topology -- Core, Operator Image, Agent Image, and OCI Helm Charts Release on Their Own SemVer | Accepted | 2026-07-14 |

## Summaries

### [ADR-001](ADR-001-cqrs.md): Command Query Responsibility Segregation (CQRS)

Separates write operations (commands dispatched through a middleware-enabled
CommandBus) from read operations (queries returning denormalized read models
via QueryBus), so domain aggregates stay focused on state transitions while
reads are independently optimized.

### [ADR-002](ADR-002-event-sourcing.md): Event Sourcing

Persists domain aggregates as append-only event streams instead of mutable
snapshots, providing a complete audit trail, time-travel debugging, and
simplified persistence at the cost of event schema management and
indefinite storage growth (mitigated by snapshots every 50 events).

### [ADR-003](ADR-003-sagas.md): Saga Pattern

Manages multi-step, cross-aggregate processes (failover, recovery, group
rebalancing) through a SagaManager that orchestrates named steps with
compensating actions, replacing distributed transactions with
event-triggered workflows that persist their own state.

### [ADR-004](ADR-004-sep-1766-digest-pinning.md): Preemptive Implementation of SEP-1766 and SEP-1763

Implements MCP tool digest pinning (SEP-1766) and interceptor framework
compliance (SEP-1763) before upstream spec ratification, treating Hangar as
the de facto reference implementation to capture first-mover positioning and
deliver supply-chain integrity to customers immediately.

Companion to [ADR-005](ADR-005-sep-1763-interceptor-compliance.md) (SEP-1763 Interceptor Framework Compliance).

### [ADR-005](ADR-005-sep-1763-interceptor-compliance.md): SEP-1763 Interceptor Framework Compliance

Aligns hangar-agent with the evolving SEP-1763 interceptor specification
by mapping existing proxy capabilities to spec terminology and incrementally
adding missing features (Mutator type, hook-based events, per-interceptor
failOpen, wildcard subscriptions).

Companion to [ADR-004](ADR-004-sep-1766-digest-pinning.md) (SEP-1766 Digest Pinning).

### [ADR-006](ADR-006-tetragon.md): Runtime Enforcement Strategy -- Tetragon-First, Pluggable Backend

Adopts a pluggable enforcement backend architecture with Tetragon as the
primary engine (v1.5+), KubeArmor and Falco as optional secondaries
(v2.5+), and NetworkPolicy as the v1.0 baseline -- keeping differentiation
in MCP-semantic policy compilation rather than kernel-level hooks.

### [ADR-007](ADR-007-langfuse-integration.md): Langfuse Integration for LLM Observability

Integrates with Langfuse through a Port/Adapter pattern (ObservabilityPort
with LangfuseObservabilityAdapter) to provide LLM-specific observability
(cost tracking, prompt correlation, quality evaluation) as an optional
dependency alongside existing OpenTelemetry infrastructure telemetry.

### [ADR-008](ADR-008-tasks-relay-only.md): Task Governance is Relay-Only -- Hangar is a Task Relay, Not a Task Executor

Hangar governs the call path; it does not become a job runner. It will relay and
govern tasks that upstreams emit (ownership + digest governance is built and
tested but dormant), never convert calls into tasks or own background execution.
The relay is deferred until both a real upstream emits tasks and the mcp task API
leaves `mcp.server.experimental`; in the interim, upstream task handles are
rejected with a clear error rather than passed through as unusable dead handles.

### [ADR-009](ADR-009-independent-release-topology.md): Independent Release Topology -- Core, Operator Image, Agent Image, and OCI Helm Charts Release on Their Own SemVer

Ratifies four independent release lanes -- Python core (`release-please` ->
PyPI), operator image + install manifest (tag-triggered -> GHCR), agent image
(tag-triggered -> GHCR, workflow still to be authored), and OCI Helm charts
(idempotent push -> `ghcr.io/mcp-hangar/charts`, guarded by a `Chart.yaml`
version-bump check) -- each with its own SemVer and owner, related by a
compatibility matrix rather than a shared version. Chart `appVersion` tracks the
released component image; chart `version` is independent. Docs advertises only
verified digests. Accepted as a decision, but the topology is *decided and
asleep*: a live audit found zero releases on every lane but the core, so rollout
is gated on the first operator/agent/chart releases and the GHCR/compatibility
policy (`mcp-hangar-operator#26`, `helm-charts#7`, `#453`).

## Conventions

ADR files follow the pattern `ADR-NNN-kebab-name.md` with three-digit
zero-padded numbers that are never reused or renumbered. Each ADR has a
three-line header (Status, Date, Authors), three required body sections
(Context, Decision, Consequences), and optional sections for Alternatives
Considered and References. Once accepted, ADR bodies are immutable --
changing a decision requires a new ADR. Five statuses are permitted:
Proposed, Accepted, Superseded by ADR-NNN, Deprecated, and Rejected. For the full
specification, see [ADR_AGENTS.md](https://github.com/mcp-hangar/mcp-hangar/blob/main/docs/internal/ADR_AGENTS.md).

## Quick links

- [How to propose a new ADR](https://github.com/mcp-hangar/mcp-hangar/blob/main/docs/internal/ADR_AGENTS.md#2-when-to-write-an-adr)
- [ADR governance and formatting rules](https://github.com/mcp-hangar/mcp-hangar/blob/main/docs/internal/ADR_AGENTS.md)
