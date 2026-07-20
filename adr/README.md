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
| [004](ADR-004-sep-1766-digest-pinning.md) | Preemptive Implementation of SEP-1766 (Digest Pinning) and SEP-1763 (Interceptor Framework) | Accepted (partial → [010](ADR-010-retire-agent-cloud-tier.md)) | 2026-05-01 |
| [005](ADR-005-sep-1763-interceptor-compliance.md) | SEP-1763 Interceptor Framework Compliance | Superseded by [010](ADR-010-retire-agent-cloud-tier.md) | 2026-05-01 |
| [006](ADR-006-tetragon.md) | Runtime Enforcement Strategy -- Tetragon-First, Pluggable Backend | Superseded by [010](ADR-010-retire-agent-cloud-tier.md) | 2026-05-10 |
| [007](ADR-007-langfuse-integration.md) | Langfuse Integration for LLM Observability | Accepted | 2026-01-12 |
| [008](ADR-008-tasks-relay-only.md) | Task Governance is Relay-Only -- Hangar is a Task Relay, Not a Task Executor | Accepted (partial → [014](ADR-014-tasks-relay-with-governance.md)) | 2026-07-02 |
| [009](ADR-009-independent-release-topology.md) | Independent Release Topology -- Core, Operator Image, Agent Image, and OCI Helm Charts Release on Their Own SemVer | Accepted (partial → [010](ADR-010-retire-agent-cloud-tier.md)) | 2026-07-14 |
| [010](ADR-010-retire-agent-cloud-tier.md) | Retire the Agent + Hangar Cloud Product Tier | Accepted | 2026-07-16 |
| [011](ADR-011-single-source-of-truth-cross-repo-facts.md) | Single Source of Truth for Cross-Repo Facts | Accepted | 2026-07-18 |
| [012](ADR-012-interceptor-sep-pin-tracking-policy.md) | Interceptor SEP-Pin Tracking Policy | Accepted | 2026-07-18 |
| [013](ADR-013-egress-policy-enforcement-model.md) | Egress Policy Enforcement Model (MCPEgressPolicy) | Accepted | 2026-07-18 |
| [014](ADR-014-tasks-relay-with-governance.md) | Tasks are Relayed With Governance -- Hangar Interposes Task Lifecycle, It Still Does Not Execute | Proposed (DRAFT) | 2026-07-20 |

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

### [ADR-010](ADR-010-retire-agent-cloud-tier.md): Retire the Agent + Hangar Cloud Product Tier

Retires the hangar-agent interceptor sidecar and the Hangar Cloud SaaS as a
product surface (repos archived; the agent chart, the core cloud connector, the
`/agent/policy` endpoint, the `--cloud-*` CLI flags, and the `agent` RBAC role
removed; terraform-provider archived). Governance stays in-process in core;
kernel-level runtime enforcement is retired with the tier. Supersedes ADR-005 and
ADR-006 fully, and ADR-004 and ADR-009 in part.

### [ADR-011](ADR-011-single-source-of-truth-cross-repo-facts.md): Single Source of Truth for Cross-Repo Facts

Every fact shared across repos (domain, released versions, install commands,
server security behavior, version compatibility) gets exactly one owner;
everything else links to or generates from it, never hand-copies. Preference
order: link > generate > hand-copy, with a reusable CI lint guarding the domain
where a value must appear literally. The governing decision for epic #501;
resolves the four drift symptoms (#485/#486/helm#44/operator#36) as
implementations rather than one-off edits.

### [ADR-012](ADR-012-interceptor-sep-pin-tracking-policy.md): Interceptor SEP-Pin Tracking Policy

The in-process interceptor surface validates against a locally-vendored schema
derived from an experimental upstream pin (`experimental-ext-interceptors @
99bc7c9`, SEP-2133) that has already renumbered and may still move. Policy:
vendor + freeze at a known-good SHA, bump only on a deliberate cadence (not
reactively), keep the surface experimental + off-by-default (capability-
negotiated), and run a scheduled drift check so re-pins are planned. Revisit
toward a hard freeze once the SEP is accepted. Governs the interceptor pin that
survived ADR-010's retirement of the (superseded) ADR-005 surface. From #488.

### [ADR-013](ADR-013-egress-policy-enforcement-model.md): Egress Policy Enforcement Model (MCPEgressPolicy)

Fixes the enforcement model for the policy language above the binary
registration switch that phases 1–3 (operator #50/#51/#52, v0.13.0) delivered.
Decision: explicit-proxy enforcement plus a policy-generated network backstop —
L7 (tools/arguments/responses) is enforced on the connections Hangar already
originates, and policy compilation generates the L3/L4 default-deny/`toFQDNs`
backstop so the data plane cannot be bypassed. No transparent TLS interception
and no eBPF protocol parsing in v1 (both rejected as over-broad for the trust
they add). Introduces the `MCPEgressPolicy` CRD (Audit-default, `targetRef`,
deny-by-default upstream allow-list referencing existing digest/approval/issuer
primitives, deterministic argument limits only). Trust boundary stated verbatim:
a policy without the backstop is a suggestion. From epic #53.

### [ADR-014](ADR-014-tasks-relay-with-governance.md): Tasks are Relayed With Governance -- Hangar Interposes Task Lifecycle, It Still Does Not Execute

**Proposed (DRAFT — awaiting maintainer ratification.)** Partially supersedes
ADR-008. Two facts changed since the relay-only decision: the SDK v2 beta
(mcp 2.0.0b2, spike #547) promotes Tasks out of `experimental` into a first-class
negotiated extension (clearing ADR-008 trigger (b)), and the built-but-dormant
governance stack (#319/#320/#321/#322) is stranded. Decision: **relay-with-governance**
— Hangar relays upstream-created tasks and interposes governance (ownership, digest
re-verification, consent) at the proxy/store seam, recording `task_id`→provenance as an
append-only event chain (ADR-002). It still does **not** execute: no task creation, no
scheduler, no worker→main-loop bridge. Lifts only ADR-008's "relay-only *permanently*"
and "do not build yet"; carries the rest forward. Build the seam now (trigger (b) met),
activate per-upstream on first real task; behavior is unchanged until then. Unblocks the
p1-high consent gate #322. Answers PR #368's objections point by point.

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
