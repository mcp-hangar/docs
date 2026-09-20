# ADR-029: One Enrichment Boundary and a Bounded Decision Vocabulary for Traces

**Status:** Proposed
**Date:** 2026-09-19
**Authors:** MCP Hangar Team

## Context

Hangar's traces became structurally correct in 2.19 (#1308–#1331): one request is one trace entered through the mcp SDK's SERVER span, `batch.call.<tool>` nests under `batch.execute`, the upstream CLIENT span carries its own carriers and outcome, the concurrency wait is measured on its own, caught failures end in ERROR with a bounded `error.type`, and export is proven end to end against a real OTLP receiver (#1293).

What traces still cannot do is explain *decisions*: why a gate refused, which backend was chosen, what an L7 policy said, or how background work relates to the call that caused it. Every task that would add this (#1278, #1285, #1286, #1295, #1297, #1279, #1281, #1288, #1296) needs the same answers first. Without one contract, each would invent its own.

The state of the published 2.21.0 wheel, re-checked on `main`, that forces the decision:

- **The request-entry span is not Hangar's, and it is not always a trace root.** The mcp SDK's `OpenTelemetryMiddleware` is on by default and never removed. It opens one SERVER span per inbound message, named `{method} {target}`, with `context=extract_trace_context(ctx.meta)` — so a caller that sends a valid W3C `traceparent` in `_meta` makes that span the child of a remote span, and it is a trace *root* only when no valid remote parent is extracted. It sets `mcp.method.name`, `mcp.protocol.version`, `jsonrpc.request.id`, `gen_ai.operation.name=execute_tool` and `gen_ai.tool.name`, and declares no semconv schema.
- **`record_exception=False` on that span is narrower than it sounds.** It disables the context manager's automatic recording only. The middleware still writes status descriptions by hand: `set_status(ERROR, e.error.message)` for an `MCPError`, and `record_exception(e)` plus `set_status(ERROR, str(e))` for anything else — a `ValidationError` is the single sanitised case. That span is not opened through Hangar's `_TextFreeTracer`, so Hangar's text-free discipline does not reach it.
- **The gate chain is thirteen stages.** `_GATES` runs `cancelled_before_execution`, `global_timeout`, `resolve_target`, `tool_access`, `withdrawal`, `digest_pin`, `circuit_breaker`, `validators`, `tenant_budget`, `approval`, `cold_start`, `deferred_digest_pin` and `cancelled_after_cold_start`. `rate_limit.check` is not one of them: it is command-bus middleware.
- **No semantic-convention pin exists.** There is no `SEMCONV_VERSION` in `src/`; this ADR establishes one.
- **Governance enrichment is dead-wired.** `set_governance_attributes` has one caller, `TracedMcpServerService`, which nothing in `src/` constructs, so the decorator [ADR-007](ADR-007-langfuse-integration.md) prescribes traces nothing on the real call paths.
- **A refusal looks like a failure, on two different paths.** A refusing gate in the executor's chain returns a `CallResult` with `success=False`, and `executor.py:1556-1561` marks the span ERROR for any such result — the same status an upstream failure gets. Two classes of refusal never take that path: an L7 deny or approval requirement **raises** (`EgressPolicyDeniedError`, `EgressPolicyApprovalRequiredError`), and a rate-limit refusal raises `RateLimitExceeded` in command-bus middleware. `_TextFreeTracer.start_as_current_span` marks a span ERROR on any escaping exception, so one L7 deny also ends `rate_limit.check`, `handler.InvokeToolCommand`, `command.send.InvokeToolCommand` and `invoke_with_retry` in ERROR. Both paths contradict the #1272 rule that only operational failures are ERROR. A refused *flat* call has a third shape: `_flat_call_tool` returns `CallToolResult(isError=True)`, which the SDK middleware matches to set its SERVER span ERROR with `error.type=tool_error`.
- **`mcp.server.id` changes meaning within one trace.** On the live tool-call path: logical target on `batch.call.<tool>`, `concurrency.acquire`, `policy.check_access`, `approval_gate.check`, `approval_gate.flow` and `invoke_with_retry`; selected member on `mcp_server.cold_start` and `command.send.InvokeToolCommand`. Only that member-valued pair has to change.
- **No causal envelope exists.** Task events carry `correlation_id` and `tenant_id`, peer events carry `produced_by`, and none carries an origin trace context.
- **Revision provenance exists only for L7**, where `policy_id` is a content hash. No configuration revision exists anywhere in `src/`.
- **The domain is already SDK-free.** `domain/` imports no OpenTelemetry or tracing module.

## Decision

### 1. Signal ownership

| Signal | Owns | Must not |
| --- | --- | --- |
| Span | An operation on the request path with its own duration: gate, cold start, wait, dispatch, upstream call | Stay open across a multi-request lifetime (tasks, timers, single-flight leaders) |
| Span attribute | Bounded facts about that operation's outcome: decision, outcome, reason code, revision | Carry payloads, free text or unbounded values |
| Span event | Rare, instant facts inside a live span | Duplicate an attribute |
| Link | Causality across traces: a shared cause, work that outlives the request, another instance, a timer, an inbound carrier from a different trace | Be invented when the cause is unknown |
| Log record | Audit (OTLP audit records), correlated to the current span only as far as #1293 proves | Be the only record of a security decision |
| Metric | Aggregates and SLOs | Carry per-request identity or free text in labels |
| Audit (durable store and OTLP) | The sampling-independent record of security-relevant decisions | Depend on trace sampling |

### 2. Parent versus link

- **Parent** only when the child's work runs synchronously on behalf of the parent, within the same request lifetime.
- **Link** when: many waiters share one cause (single-flight cold start, #1279); the work outlives the request (governed tasks, #1281); the cause is on another instance (tailed peer events, #1288); the cause is a timer or scheduler (#1296); an inbound carrier names a different trace than the ambient span (already implemented, #1316).
- **Never:** `correlation_id` as a parent; a span held open across a multi-hour task; an invented parent or link when the origin is unknown or malformed.

### 3. The SDK SERVER span is the request-entry span, not necessarily the trace root

Hangar never opens a parallel request span. The SDK's SERVER span is where a request enters Hangar and is the topmost span of that request inside it; it is a *trace root* only when no valid remote parent was extracted from `_meta`. With a valid inbound carrier the trace continues from the caller's span, and Hangar's spans are descendants of it.

`hangar_call` is the SERVER span's child, `batch.execute` is `hangar_call`'s child, `batch.call.<tool>` is `batch.execute`'s child. Flat tools enter as SERVER → `batch.execute` → `batch.call.<tool>`. `execute_tool <tool>` (CLIENT) is the only upstream call span. Names and existing attributes are kept; the one exception is named in Decision 5.

### 4. One governance enrichment boundary

- `BatchExecutor._execute_call`'s `batch.call.<tool>` span is the single enrichment point for MCP tool calls; batch and flat-tool invocations both pass through it. Caller and tenant attributes come only from the bound identity context, never from baggage, and unknown values are omitted. The per-gate outcome summary lives here.
- Management and REST commands that do not reach the executor get the dispatch span of #1297, with the same outcome vocabulary.
- **`TracedMcpServerService` is retired** (#1278 deletes it). Reviving it would rebuild a parallel pipeline on a path nothing constructs.
- **Relationship to [ADR-007](ADR-007-langfuse-integration.md):** nothing in it is superseded. Its port and adapter design stands, and the Langfuse adapter is driven from this boundary rather than from the decorator its Key Design Decision 2 describes. That decorator is retired in implementation by #1278; the ADR that prescribed it keeps its status. Its port shape is unchanged — an adapter may receive process-local invocation data — but every emission that leaves the process is subordinate to the #1276 data-handling contract, which decides what an adapter is permitted to send. The Langfuse scrub defaults currently contradict each other on that point (#1534); this ADR does not depend on which way that is resolved.

### 5. A bounded decision vocabulary under `hangar.`

Four vocabularies, one per layer that can stop or steer a call, because those layers have different owners and lifecycles. A term never crosses layers.

| Vocabulary | Covers | Task |
| --- | --- | --- |
| `hangar.gate.*` | exactly the stages of `_GATES` in the batch executor | #1285 |
| `hangar.l7.*` | the egress policy verdict, which is raised rather than gated | #1295 |
| `hangar.dispatch.*` | command-bus and management rejections, including `rate_limit.check` | #1297 |
| `hangar.route.*` | target resolution and member selection | #1286 |

**A gate is a stage of `_GATES`, and nothing else.** `rate_limit.check` is command-bus middleware and belongs to `hangar.dispatch.*`; an L7 verdict is raised from the aggregate and belongs to `hangar.l7.*`. Naming them gates would make the word mean "anything that can stop a call", which is not a set the code has.

#### Gate decisions are span events, not scalar attributes

One call passes many gates. A scalar attribute holds one value per key, so the last gate to write would erase every decision before it. Each gate that runs, or is explicitly skipped, records one bounded event on `batch.call.<tool>`:

| Event | Attributes |
| --- | --- |
| `hangar.gate.decision` | `hangar.gate.name`, `hangar.gate.outcome`, optional `hangar.gate.reason`, optional `hangar.gate.revision` |

A deferred digest pin therefore records `{name=digest_pin, outcome=deferred}` and, on the same span, later records `{name=digest_pin, outcome=allow|deny|error}`. Neither overwrites the other.

The call's summary is separate and scalar. It never carries a history.

| Key | Values |
| --- | --- |
| `hangar.gate.name` | exactly the thirteen `_GATES` stages without their `_gate_` prefix: `cancelled_before_execution`, `global_timeout`, `resolve_target`, `tool_access`, `withdrawal`, `digest_pin`, `circuit_breaker`, `validators`, `tenant_budget`, `approval`, `cold_start`, `deferred_digest_pin`, `cancelled_after_cold_start`. A stage added to `_GATES` takes its name by the same rule. |
| `hangar.gate.outcome` | `allow` (passed), `deny` (refused), `skip` (not applicable to this call), `deferred` (decided later on the same call), `error` (the gate itself failed) |
| `hangar.gate.reason` | a bounded code list per gate, defined next to the gate and documented; never free text |
| `hangar.call.outcome` | `allow`, `deny`, `error` |
| `hangar.refusal.gate`, `hangar.refusal.reason` | the first refusing gate, and its reason |
| `hangar.l7.verdict` | `allow`, `audit_observed`, `deny`, `require_approval`, `approval_honored` |
| `hangar.l7.mode`, `hangar.l7.rule_kind` | the lowercased `PolicyMode` — `audit`, `enforce`, while the API spelling stays `Audit`/`Enforce` per [ADR-013](ADR-013-egress-policy-enforcement-model.md); `tool`, `argument`, `header` |
| `hangar.dispatch.outcome` | `success`, `rejected`, `error`; a command-bus rate limit is `rejected` |
| `hangar.route.backend`, `hangar.route.reason` | the selected member; `standalone`, `load_balanced`, `pinned`, `canary`, `canary_fallback`, `no_available_member` |

#### Span status

| Situation | Status on Hangar-owned spans |
| --- | --- |
| Expected refusal: any gate `deny`, an L7 `deny` or `require_approval`, a dispatch rejection | UNSET |
| Operational failure: the call or the gate machinery broke | ERROR, with a bounded `error.type` |
| Upstream tool failure: the upstream was reached and failed | ERROR on `execute_tool <tool>` and on `batch.call.<tool>` |
| Evaluator failure, even when the fail-closed verdict is a denial | ERROR — the verdict is a refusal, but the evaluator still broke |

Rules:

- **This binds Hangar-owned spans only.** ERROR-for-operational-failures governs the spans Hangar opens through `_TextFreeTracer`. The SDK-owned SERVER span follows MCP SDK response semantics and stays ERROR for a `CallToolResult(isError=true)` refusal, so a governance denial on the flat path produces a trace whose entry span is ERROR above a `batch.call.<tool>` that is UNSET. That deviation is accepted and recorded here rather than left to be discovered. Overriding it would mean writing to a span Hangar does not own, and OpenTelemetry does not let a status return to UNSET — the only available override is `OK`, which asserts more about an SDK-owned response than Hangar is entitled to claim.
- **A refusal carried by an exception leaves no ERROR behind it.** L7 denials, approval requirements and command-bus rate limits are *raised*, and `_TextFreeTracer` marks every span they escape as ERROR. Those spans — `rate_limit.check`, `handler.*`, `command.send.*`, `invoke_with_retry` — are UNSET for a refusal. The tracer therefore has to tell a refusal exception from a failure instead of treating every escape alike; that is part of #1285 and #1295, not an implementation detail left to each.
- **The first refusing gate is identifiable.** No downstream gate, cold-start or invoke span appears after it, and it is what `hangar.refusal.gate` names.
- **No invented reasons.** An engine returning only a boolean gets an extended port result. If it cannot say why, `hangar.gate.reason` is omitted.
- **`mcp.server.id` always means the logical target,** on every span, because one attribute that means two things cannot be queried; the concrete member is `hangar.route.backend`. The logical target is what the caller named and what policy, quota and audit are keyed on, so it is the identity that has to be constant across the trace, while the member is a routing outcome that can change between retries of one call. **This is a compatibility change, not an additive one:** `mcp_server.cold_start` and `command.send.InvokeToolCommand` carry the member today, and queries reading them as the concrete backend must move to `hangar.route.backend`. #1286 owns it and ships it with a changelog and migration note.
- **The log side widens to match the gate vocabulary.** `_log_call_failure` keys `refused` on two error types only (`EgressPolicyDeniedError`, `EgressPolicyApprovalRequiredError`), so a gate denial would read `hangar.gate.outcome=deny` on the span and `batch_call_failed` in the log. Any expected refusal logs as `batch_call_refused` at warning with its bounded reason, so one denial is one word in both places. This raises warning volume above today's L7-only behaviour, and that is accepted.

### 6. Revision provenance

| Decision | Revision source | Key |
| --- | --- | --- |
| L7 egress | `policy_id` (content hash) | `hangar.l7.policy_id` |
| Digest pin | the pinned schema digest | `hangar.gate.revision` |
| Approval | `approval.id` | `approval.id` |
| Tool access policy, validators, routing | none exists | omitted until a configuration revision source exists; never fabricated |

### 7. The domain stays SDK-free

A decision made inside an aggregate leaves through a narrow domain port with a no-op default, or a defaulted observational field on the existing `Decision`. An application or infrastructure adapter writes the span attributes. Existing domain events such as `EgressPolicyViolationObserved` are the preferred carriers. Telemetry never runs a second policy evaluation; #1322 is the precedent.

### 8. Causal envelope

- **Stored** as an optional bounded value: the W3C `traceparent` string of the originating span, as data and never as an SDK object — the event `metadata` column (#1288), the task ledger entry (#1281), the timer payload (#1296).
- **Consumed** by opening a new span with one link to that origin. Many waiters produce many links, never one shared parent.
- **Missing or malformed origin:** no link.
- **Replication.** Tailed delivery stays projection-only ([ADR-020](ADR-020-high-availability.md) §4). Replicating trace context never replays effects.

### 9. Semantic conventions

- Hangar pins the MCP and GenAI attribute definitions that `mcp==2.0.0`'s middleware emits, introduced in OpenTelemetry semantic conventions **v1.39.0** and maintained since v1.42.0 in `semantic-conventions-genai`. The pin is recorded as `SEMCONV_VERSION` in `observability/conventions.py`, which does not exist yet. The compatibility baseline is reviewed on **every** `mcp` dependency bump, and the pin may also be advanced independently when Hangar deliberately adopts a newer semantic-convention version; either way the change reviews the GenAI/MCP changelog for attribute and span-semantic changes.
- **Documented deviations, not renamed:** `batch.call.<tool>`, `mcp.server.id`, `deployment.environment`, audit's `mcp.error.type`.
- **Additive, with one named exception.** Every `hangar.*` key above is new surface added beside what exists. The one change to an existing attribute is `mcp.server.id` on `mcp_server.cold_start` and `command.send.InvokeToolCommand`, owned by #1286 and shipped with a migration note. Live code uses the `conventions.py` constants instead of string literals; unused constants are deleted or marked reserved.

### 10. Privacy and sampling

Every attribute, reason code and link above passes the data-handling allowlist decided in #1276 before it is emitted: caller user and agent ids on spans are opt-in only, span attributes are limited to 256 characters, and status descriptions and exception events are bounded by that same contract. Sampling never decides audit durability.

### 11. What the contract produces on the live paths

What the rules above produce on the paths that exist today. Each row is the contract #1278, #1285, #1286, #1295 and #1297 implement, not a separate decision any of them may take.

| Case | Spans and status | Recorded as |
| --- | --- | --- |
| **Flat refusal** — governance denies, `CallToolResult(isError=True)` reaches the wire | SDK SERVER **ERROR** (SDK-owned, `error.type=tool_error`); `batch.execute` UNSET; `batch.call.<tool>` **UNSET** | `hangar.gate.decision` for each gate; `hangar.call.outcome=deny`; `hangar.refusal.gate` names the first refusing gate |
| **L7 deny** — `EgressPolicyDeniedError` raised through the stack | `batch.call.<tool>`, `invoke_with_retry`, `command.send.InvokeToolCommand`, `handler.InvokeToolCommand` all **UNSET** | `hangar.l7.verdict=deny` with `hangar.l7.mode` and `hangar.l7.policy_id`; `hangar.call.outcome=deny` |
| **Tenant budget deny** — `_gate_tenant_budget` refuses | `batch.call.<tool>` **UNSET**; no cold-start or invoke span after it | `hangar.gate.decision {name=tenant_budget, outcome=deny}` with a bounded reason |
| **Deferred digest** — pin deferred, then rechecked on the same call | `batch.call.<tool>` carries both decisions | two `hangar.gate.decision` events: `{name=digest_pin, outcome=deferred}`, then `{name=deferred_digest_pin, outcome=allow\|deny\|error}` |
| **Command rate limit** — refused in command-bus middleware, outside `_GATES` | `rate_limit.check` and the spans it escapes **UNSET** | `hangar.dispatch.outcome=rejected`; it is not a gate and takes no `hangar.gate.*` key |
| **Group routing** — logical target differs from the selected member | — | `mcp.server.id` is the logical target on `batch.call.<tool>`, `mcp_server.cold_start` and `command.send.InvokeToolCommand` alike; `hangar.route.backend` carries the member on the spans that selected it |
| **Evaluator failure** — the engine breaks and the fail-closed verdict is a denial | the evaluating span **ERROR** with a bounded `error.type` | the denial is still recorded as an outcome; a broken evaluator is not a refusal |

## Consequences

### Positive

One boundary, one vocabulary and one parent/link rule unblock #1278, #1285, #1286, #1295, #1297 and #1279, #1281, #1288, #1296 — none has to invent its own. Denials stop inflating error rates on the spans Hangar owns, and the first refusing gate becomes queryable by name. Recording each gate as a span event means a call's full decision history survives instead of the last gate overwriting the rest. Five implementers can take #1278, #1285, #1286, #1295 and #1297 and produce compatible telemetry without another semantic decision. The dead path ADR-007 pointed at is retired rather than revived.

### Negative

The status of refused spans changes across the Hangar-owned tree, not only on `batch.call.<tool>`; dashboards and alerts keyed on ERROR must be reviewed, including the Helm-owned ones in mcp-hangar/helm-charts. **`mcp.server.id` changes value on two spans** — a compatibility change, not an additive one, and queries reading it there as the concrete backend must move to `hangar.route.backend`. A trace whose entry span is ERROR above an UNSET `batch.call.<tool>` is now an expected shape on the flat path, and anyone reading the entry span alone will still count governance denials as errors. Telling a refusal exception from a failure inside the tracer is new work that #1285 and #1295 both depend on. `hangar.*` is new surface to keep stable, and revision stays absent for most decision types.

### Neutral

Hangar depends on the SDK middleware staying on by default, and nothing asserts that today. The integration trace tests observe a `tools/call hangar_call` span, which depends on the middleware only incidentally; a contract test that fails by naming the middleware still has to be written.

The #1276 data-handling contract reaches Hangar-owned spans through `_TextFreeTracer`. The SDK-owned SERVER span does not go through it: `record_exception=False` disables only the context manager's automatic recording, while the middleware still sets status descriptions by hand and calls `record_exception` for a generic exception. So #1276's guarantees apply directly to Hangar's spans, and to the SERVER span only if it is separately adapted or verified. This ADR does not assume it is.

## Alternatives Considered

1. **Revive `TracedMcpServerService` and wire it in** — rejected: it decorates a service no path constructs, so reviving it rebuilds a parallel pipeline.
2. **A Hangar-owned request span beside the SDK's** — rejected: two roots per request, and the SDK span already parents from `_meta`.
3. **Reuse the existing `mcp.*` and `policy.*` keys** — rejected: needs renames or overloads existing semantics; the `hangar.*` additions keep old queries working.
4. **Parent tasks and peer events on the originating span** — rejected: long-lived or cross-process parents, and one parent for many waiters. Links are the OpenTelemetry-correct form.
5. **Keep ERROR for refusals, or phase it over two releases** — rejected: keeping ERROR leaves denials inflating error rates; a two-release transition doubles the work for a change a changelog note covers.

## References

- mcp-hangar/mcp-hangar#1275 (this decision's issue), #1276 (the data-handling contract), #1264 (the tracing epic).
- [ADR-007](ADR-007-langfuse-integration.md), [ADR-013](ADR-013-egress-policy-enforcement-model.md), [ADR-014](ADR-014-tasks-relay-with-governance.md), [ADR-016](ADR-016-approval-resolution-chokepoint.md), [ADR-020](ADR-020-high-availability.md).
- OpenTelemetry semantic conventions v1.39.0 (open-telemetry/semantic-conventions#2043, #2083); `open-telemetry/semantic-conventions-genai`.
