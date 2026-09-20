# ADR-029: One Enrichment Boundary and a Bounded Decision Vocabulary for Traces

**Status:** Proposed
**Date:** 2026-09-19
**Authors:** MCP Hangar Team

## Context

Hangar's traces became structurally correct in 2.19 (#1308–#1331): one request is one trace rooted in the mcp SDK's SERVER span, `batch.call.<tool>` nests under `batch.execute`, the upstream CLIENT span carries its own carriers and outcome, the concurrency wait is measured on its own, caught failures end in ERROR with a bounded `error.type`, and export is proven end to end against a real OTLP receiver (#1293).

What traces still cannot do is explain *decisions*: why a gate refused, which backend was chosen, what an L7 policy said, or how background work relates to the call that caused it. Every task that would add this (#1278, #1285, #1286, #1295, #1297, #1279, #1281, #1288, #1296) needs the same answers first. Without one contract, each would invent its own.

The state of the code at `9821f47b` that forces the decision:

- **The request root is not Hangar's.** The mcp SDK's `OpenTelemetryMiddleware` is on by default and never removed. It opens one SERVER span per inbound message, named `{method} {target}`, parented from `params._meta`, setting `mcp.method.name`, `mcp.protocol.version`, `jsonrpc.request.id`, `gen_ai.operation.name=execute_tool` and `gen_ai.tool.name`, with `record_exception=False` and no declared semconv schema.
- **Governance enrichment is dead-wired.** `set_governance_attributes` has one caller, `TracedMcpServerService`, which nothing in `src/` constructs, so the decorator [ADR-007](ADR-007-langfuse-integration.md) prescribes traces nothing on the real call paths.
- **A refusal looks like a failure, on two different paths.** A refusing gate in the executor's chain returns a `CallResult` with `success=False`, and `executor.py:1556-1561` marks the span ERROR for any such result — the same status an upstream failure gets. Two classes of refusal never take that path: an L7 deny or approval requirement **raises** (`EgressPolicyDeniedError`, `EgressPolicyApprovalRequiredError`), and a rate-limit refusal raises `RateLimitExceeded` in command-bus middleware. `_TextFreeTracer.start_as_current_span` marks a span ERROR on any escaping exception, so one L7 deny also ends `rate_limit.check`, `handler.InvokeToolCommand`, `command.send.InvokeToolCommand` and `invoke_with_retry` in ERROR. Both paths contradict the #1272 rule that only operational failures are ERROR.
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

### 3. The SDK SERVER span is the request root

Hangar never opens a parallel request span. `hangar_call` is the SERVER span's child, `batch.execute` is `hangar_call`'s child, `batch.call.<tool>` is `batch.execute`'s child. Flat tools enter as SERVER → `batch.execute` → `batch.call.<tool>`. `execute_tool <tool>` (CLIENT) is the only upstream call span. All additive: existing names and attributes are kept.

### 4. One governance enrichment boundary

- `BatchExecutor._execute_call`'s `batch.call.<tool>` span is the single enrichment point for MCP tool calls; batch and flat-tool invocations both pass through it. Caller and tenant attributes come only from the bound identity context, never from baggage, and unknown values are omitted. The per-gate outcome summary lives here.
- Management and REST commands that do not reach the executor get the dispatch span of #1297, with the same outcome vocabulary.
- **`TracedMcpServerService` is retired** (#1278 deletes it). Reviving it would rebuild a parallel pipeline on a path nothing constructs.
- **Relationship to [ADR-007](ADR-007-langfuse-integration.md):** nothing in it is superseded. Its port and adapter design stands, and the Langfuse adapter is driven from this boundary rather than from the decorator its Key Design Decision 2 describes. That decorator is retired in implementation by #1278; the ADR that prescribed it keeps its status.

### 5. A bounded outcome and reason vocabulary under `hangar.`

| Key | Values | Task |
| --- | --- | --- |
| `hangar.gate.name` | the gate's name in `_GATES` without its `_gate_` prefix — `cancelled_before_execution`, `global_timeout`, `resolve_target`, `tool_access`, `withdrawal`, `digest_pin`, `circuit_breaker`, `validators`, `tenant_budget`, `approval`, `cold_start`, `deferred_digest_pin`, `cancelled_after_cold_start` — plus `egress_l7` and `rate_limit`, which refuse by raising rather than from that chain. A gate added to `_GATES` takes its name by the same rule, which is what keeps the list bounded without freezing it. | #1285 |
| `hangar.gate.outcome` | `allow`, `deny`, `skip`, `deferred`, `error` | #1285 |
| `hangar.gate.reason` | a bounded code list per gate, defined next to the gate and documented; no free text | #1285 |
| `hangar.l7.verdict` | `allow`, `audit_observed`, `deny`, `require_approval`, `approval_honored` | #1295 |
| `hangar.l7.mode`, `hangar.l7.rule_kind` | the lowercased `PolicyMode` — `audit`, `enforce`, while the API spelling stays `Audit`/`Enforce` per [ADR-013](ADR-013-egress-policy-enforcement-model.md); `tool`, `argument`, `header` | #1295 |
| `hangar.route.backend`, `hangar.route.reason` | the selected member; `standalone`, `load_balanced`, `pinned`, `canary`, `canary_fallback`, `no_available_member` | #1286 |
| `hangar.dispatch.outcome` | `success`, `rejected`, `error` | #1297 |

Rules:

- **A refusal is a correct answer, not an operational failure.** It sets `hangar.gate.outcome=deny` and leaves span status UNSET. ERROR is reserved for operational failures (#1272, #1277). This holds for every span a refusal passes through, not only `batch.call.<tool>`: a raised L7 or rate-limit refusal must also leave `rate_limit.check`, `handler.*`, `command.send.*` and `invoke_with_retry` UNSET, so the tracer's blanket exception handling has to tell a refusal from a failure. It ships in **one release** with #1285, with a changelog note that error-rate panels stop counting denials and `hangar.gate.outcome=deny` is the new query.
- **The first refusing gate is identifiable.** No downstream gate, cold-start or invoke span appears after it.
- **No invented reasons.** An engine returning only a boolean gets an extended port result. If it cannot say why, `hangar.gate.reason` is omitted.
- **`mcp.server.id` always means the logical target.** The selected member goes to `hangar.route.backend`. The member-valued occurrences (`mcp_server.cold_start`, `command.send.InvokeToolCommand`) change in **#1286**, with their changelog.
- **The log-side refusal notion widens to match the gate vocabulary.** `_log_call_failure` keys `refused` on two error types only (`EgressPolicyDeniedError`, `EgressPolicyApprovalRequiredError`), so a gate denial would read `hangar.gate.outcome=deny` on the span and `batch_call_failed` in the log. Any gate refusal logs as `batch_call_refused` at warning instead, so one denial is one word in both places. This raises warning volume above today's L7-only behaviour, and that is accepted.

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

- Hangar pins the MCP and GenAI attribute definitions that `mcp==2.0.0`'s middleware emits, introduced in OpenTelemetry semantic conventions **v1.39.0** and maintained since v1.42.0 in `semantic-conventions-genai`. The pin is recorded as `SEMCONV_VERSION` in `observability/conventions.py` and bumped with the `mcp` dependency, reviewing that repository's changelog for renames.
- **Documented deviations, not renamed:** `batch.call.<tool>`, `mcp.server.id`, `deployment.environment`, audit's `mcp.error.type`.
- **Additive only.** Live code uses the `conventions.py` constants instead of string literals; unused constants are deleted or marked reserved.

### 10. Privacy and sampling

Every attribute, reason code and link above passes the data-handling allowlist decided in #1276 before it is emitted: caller user and agent ids on spans are opt-in only, span attributes are limited to 256 characters, and status descriptions and exception events are bounded by that same contract. Sampling never decides audit durability.

## Consequences

### Positive

One boundary, one vocabulary and one parent/link rule unblock #1278, #1285, #1286, #1295, #1297 and #1279, #1281, #1288, #1296 — none has to invent its own. Denials stop inflating error rates on the spans Hangar owns, and the first refusing gate becomes queryable. The SDK's SERVER span is not one of them: a refused flat-tool call returns `CallToolResult(isError=True)`, which the SDK middleware matches to set the request root ERROR with `error.type=tool_error`. Decision 9 keeps that span unrenamed and the SDK offers no hook, so the root remains a documented deviation. The dead path ADR-007 pointed at is retired rather than revived.

### Negative

The status of refused `batch.call.<tool>` spans changes; dashboards and alerts keyed on ERROR must be reviewed, including the Helm-owned ones in mcp-hangar/helm-charts. `hangar.*` is new surface to keep stable. Revision stays absent for most decision types. Pinning Development-stability conventions needs a bump process tied to `mcp` upgrades.

### Neutral

Hangar depends on the SDK middleware staying on by default, and nothing asserts that today. The integration trace tests observe a `tools/call hangar_call` span, which depends on the middleware only incidentally; a contract test that fails by naming the middleware still has to be written.

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
