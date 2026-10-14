# Architecture Decision Records

This register identifies the current architectural decisions and the records they replaced. Historical ADR bodies preserve their original context; a retired component named there is not an instruction to rebuild it.

## How to read the register

Decision status and implementation evidence answer different questions:

- **Proposed:** a decision awaits review and acceptance.
- **Accepted:** the architectural choice is recorded. This does not prove
  every implementation path, deployment or promised guarantee is complete.
- **Superseded by ADR-NNN:** a later record replaces the decision.
- **Deprecated:** the decision is no longer recommended and has no named
  replacement record.
- **Rejected:** a proposal was explicitly declined.

Implementation progress and release evidence are maintained below and in the linked issues. Do not put deployment state, activation dates or partial implementation into the decision-status enum.

## Current decisions

| ADR | Title | Governing decision |
| --- | --- | --- |
| [001](ADR-001-cqrs.md) | Command Query Responsibility Segregation (CQRS) | Commands and queries have separate dispatch contracts. |
| [003](ADR-003-sagas.md) | Saga Pattern | Multi-step recovery and failover use sagas. |
| [004](ADR-004-sep-1766-digest-pinning.md) | Preemptive Implementation of SEP-1766 (Digest Pinning) and SEP-1763 (Interceptor Framework) | Core retains tool-contract digest pinning; the agent/cloud split was retired by ADR-010. |
| [008](ADR-008-tasks-relay-only.md) | Task Governance is Relay-Only -- Hangar is a Task Relay, Not a Task Executor | Hangar remains a relay rather than an executor; the deferral was replaced by ADR-014. |
| [009](ADR-009-independent-release-topology.md) | Independent Release Topology -- Core, Operator Image, Agent Image, and OCI Helm Charts Release on Their Own SemVer | Core, operator and charts release independently; ADR-010 retired the agent lane. |
| [010](ADR-010-retire-agent-cloud-tier.md) | Retire the Agent + Hangar Cloud Product Tier | The agent/cloud product tier is retired; governance runs in core. |
| [011](ADR-011-single-source-of-truth-cross-repo-facts.md) | Single Source of Truth for Cross-Repo Facts | Cross-repository facts have one owner; consumers link or generate. |
| [012](ADR-012-interceptor-sep-pin-tracking-policy.md) | Interceptor SEP-Pin Tracking Policy | Interceptor schemas are vendored and updated by deliberate review. |
| [013](ADR-013-egress-policy-enforcement-model.md) | Egress Policy Enforcement Model (MCPEgressPolicy) | MCP-semantic L7 enforcement is paired with a generated network backstop. |
| [014](ADR-014-tasks-relay-with-governance.md) | Tasks are Relayed With Governance -- Hangar Interposes Task Lifecycle, It Still Does Not Execute | Upstream tasks are relayed with governance, never executed by Hangar. |
| [015](ADR-015-vendored-task-wire.md) | The Tasks Wire is Vendored -- `mcp_types.Task*` is a Fossil, Not a Moving Target | The served task wire is vendored; capability advertising follows served behavior. |
| [016](ADR-016-approval-resolution-chokepoint.md) | Approval Resolution Has One Authorized Chokepoint, and Core Knows No Vendors | Approval resolution passes one authorizing command handler. |
| [017](ADR-017-approval-input-request-namespace.md) | Pending Approvals Use `io.mcp-hangar/approval`, and Carry No Requested Schema | Pending approvals use the owned approval namespace. |
| [018](ADR-018-event-sourcing-actually-wired.md) | Event Sourcing, Actually Wired -- and What Is Not Event-Sourced | The event log persists aggregate history on the real publication path. |
| [019](ADR-019-one-storage-decision-two-backends.md) | One Storage Decision, and Two Backends That Are Never Mixed | One backend selection provides the complete persistence bundle. |
| [020](ADR-020-high-availability.md) | More Than One Gateway -- What Is Shared, What Is Leased, and What Stays Local | Fleet state is shared while resource-local state and selected controls stay local. |
| [021](ADR-021-config-file-endpoints-outside-the-ssrf-policy.md) | A Remote Upstream in the Configuration File Stays Outside the SSRF Policy | Configuration-file remote endpoints are operator-trusted; API endpoints use SSRF policy. |
| [022](ADR-022-the-management-surface-is-what-the-caller-may-call.md) | The Management Surface Is Whatever the Caller Is Allowed to Call | Front-door management visibility follows the caller's permissions. |
| [023](ADR-023-mcp-registry-listing.md) | The MCP Registry Entry Describes a Package, Not a Service | The MCP Registry entry describes the installable package, not a hosted endpoint. |
| [024](ADR-024-approval-hold-belongs-on-a-tool-call.md) | A Human Approval Hold Belongs on a Tool Call, Not on a Fetch | Human approval holds belong to tool calls, not prompt/resource fetches. |
| [025](ADR-025-header-selectors-must-not-match-unvalidated-headers.md) | A Header Selector Must Not Match a Header Nobody Validated | An unvalidated MCP parameter header cannot satisfy a header selector. |
| [027](ADR-027-egress-is-a-trust-mode-not-a-preset.md) | `egress` Is a Trust Mode, Not a Preset of the Front Door | Egress remains a separate no-tenant policy mode; invocation RBAC is shared. |
| [028](ADR-028-the-front-door-invoke-gate-is-the-tool-access-policy.md) | One Invoke Authorization Contract for HTTP and Stdio | HTTP and stdio preserve their identity boundaries and share enabled-auth invoke authorization. |
| [029](ADR-029-one-enrichment-boundary-and-a-bounded-decision-vocabulary.md) | One Enrichment Boundary and a Bounded Decision Vocabulary for Traces | One enrichment boundary emits bounded decisions with explicit causal and privacy contracts. |

## Historical and deprecated records

| ADR | Title | Disposition |
| --- | --- | --- |
| [002](ADR-002-event-sourcing.md) | Event Sourcing | Superseded by [ADR-018](ADR-018-event-sourcing-actually-wired.md) (the decision was never wired; ADR-018 records the shape that was actually built) |
| [005](ADR-005-sep-1763-interceptor-compliance.md) | SEP-1763 Interceptor Framework Compliance | Superseded by [ADR-010](ADR-010-retire-agent-cloud-tier.md) (the hangar-agent interceptor sidecar is retired) |
| [006](ADR-006-tetragon.md) | Runtime Enforcement Strategy -- Tetragon-First, Pluggable Backend | Superseded by [ADR-010](ADR-010-retire-agent-cloud-tier.md) (kernel-level runtime enforcement retired with the agent/cloud tier) |
| [007](ADR-007-langfuse-integration.md) | Langfuse Integration for LLM Observability | Deprecated |
| [026](ADR-026-stdio-is-an-authenticated-transport.md) | Stdio Is an Authenticated Transport, and the Config Names Its Principal | Superseded by [ADR-028](ADR-028-the-front-door-invoke-gate-is-the-tool-access-policy.md) |

ADR-007 is Deprecated because core 2.25.0 removed its dedicated Langfuse adapter and settings (mcp-hangar/mcp-hangar#1734). Langfuse can consume the existing OTLP trace export; deprecation does not retire that receiver or OpenTelemetry.

ADR-026 is superseded by ADR-028. Its process-spawn identity boundary and read-only default role are carried forward. The replaced part is the claim that invocation authorization has no effect on stdio.

## Decision relationships

Some later records replace only part of an earlier design while the rest remains in force. That relationship is stated here rather than represented as an additional status value.

| Earlier record | Later record | Relationship |
| --- | --- | --- |
| ADR-004 | ADR-010 | Retires the agent/cloud enforcement split; core digest pinning remains. |
| ADR-008 | ADR-014 | Replaces the relay deferral; retains the prohibition on becoming an executor. |
| ADR-009 | ADR-010 | Retires the agent release lane; independent release ownership remains. |
| ADR-014 | ADR-015 | Corrects the SDK wire premise and governs the served task wire. |
| ADR-019 | ADR-020 | Adds the shared-storage coordination contract. |
| ADR-026 | ADR-028 | Carries forward stdio identity and records the repaired invoke authorization. |

## Implementation evidence and remaining work

This is a living evidence map, separate from immutable accepted decisions. A merged implementation is not proof of a deployed production result. Source and tests below were reviewed for this reconciliation; no production probe was run.

| Decision | Recorded implementation evidence | Remaining acceptance or limitation |
| --- | --- | --- |
| ADR-007 / ADR-029 | [Core mcp-hangar/mcp-hangar#1734](https://github.com/mcp-hangar/mcp-hangar/pull/1734) removed the vendor adapter in 2.25.0 and retained OTLP export. | Receiver delivery must be verified for the deployment that uses it. |
| ADR-014 / ADR-015 | ADR-015 records reactivation through core mcp-hangar/mcp-hangar#645; `tests/unit/test_the_task_relay_kill_switch.py` checks the enabled/default-on path and served capabilities. | The switch may disable relay deliberately; protocol advertising must follow actual wiring. |
| ADR-027 | Separate egress/front-door tenant rules exist; the original decision issue is [core mcp-hangar/mcp-hangar#1371](https://github.com/mcp-hangar/mcp-hangar/issues/1371). | `tool_projection.flat` and the find/call surface remain future work in [core mcp-hangar/mcp-hangar#1370](https://github.com/mcp-hangar/mcp-hangar/issues/1370); this record does not advertise them as shipped. |
| ADR-028 | [Core mcp-hangar/mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623), released in 2.24.0, applies shared invoke authorization to flat/batch calls and declared stdio roles. [mcp-hangar/mcp-hangar#1631](https://github.com/mcp-hangar/mcp-hangar/pull/1631) covers stdio management authorization. | Auth-disabled behavior stays explicit; `viewer` does not acquire invoke permission under enabled auth. |
| ADR-029 | The enrichment vocabulary shipped across 2.22.0 and 2.24.0; [core #1264](https://github.com/mcp-hangar/mcp-hangar/issues/1264) tracks aggregate acceptance. | [mcp-hangar/mcp-hangar#1288](https://github.com/mcp-hangar/mcp-hangar/issues/1288) tracks peer-event causality; [mcp-hangar/mcp-hangar#1535](https://github.com/mcp-hangar/mcp-hangar/issues/1535) tracks residual telemetry-canary coverage. |
| ADR-013 | L7 delivery and network-policy objects have implementation and reachability tests. | [Operator #327](https://github.com/mcp-hangar/mcp-hangar-operator/issues/327) tracks the ingress fence; [#325](https://github.com/mcp-hangar/mcp-hangar-operator/issues/325) tracks Audit-mode blocking. Do not infer an unbypassable deployment from object creation or status alone. [Docs #471](https://github.com/mcp-hangar/docs/issues/471) owns the guarantee reconciliation. |
| ADR-019 / ADR-020 | [Core #1560](https://github.com/mcp-hangar/mcp-hangar/pull/1560) restores pushed L7 policy on durable restart paths. | [Core mcp-hangar/mcp-hangar#1306](https://github.com/mcp-hangar/mcp-hangar/issues/1306) retains deployment restart/redelivery acceptance. |
| ADR-012 | Vendored schema and drift detection separate pinning from an automatic upstream update. | [Core #1158](https://github.com/mcp-hangar/mcp-hangar/issues/1158) retains the deliberate re-pin/hold decision. |

## Open architecture decisions

These issues are proposals, not numbered or accepted ADRs:

- [docs #461](https://github.com/mcp-hangar/docs/issues/461): one typed
  configuration model and validation policy. The model decision and a future
  major-release decision are separate; this register does not approve 3.0.
- [docs #464](https://github.com/mcp-hangar/docs/issues/464): structural and
  description drift, deterministic classification and re-approval policy.
  Today's digest contract remains in force until a new decision replaces it.

## Governance

Accepted ADR bodies are historical records. A substantive decision change requires a successor with references in both directions. A status-only deprecation or supersession does not authorize rewriting the old body. A Proposed ADR can be revised before acceptance.

Maintain this register in the same PR as an ADR or status change. Keep each human-authored PR focused on one decision or reconciliation goal. New and revised proposals follow the Context, Decision and Consequences structure, including Positive and Negative consequences.

See [ADR governance](https://github.com/mcp-hangar/mcp-hangar/blob/main/docs/internal/ADR_AGENTS.md) and [Git Flow](../development/GIT_FLOW.md). Agents may draft content in issue comments; the maintainer authors the ADR PR.
