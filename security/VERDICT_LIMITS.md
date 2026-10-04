<!-- verified-against: 2.24.0 -->

# What a Verdict Establishes

Hangar's thesis is that every tool call ends in a verdict. This page is the other
half of that: what a given verdict **proves** to someone reading it later — an
auditor with a SIEM export, a second team holding a drift event, a reviewer of an
approval record.

A verdict is three things: an **outcome**, a **reason**, and the **rule that
produced it**. Read a record with all three, and note what is *not* in it. The
columns below are the shape
[`COMPLIANCE_POSTURE.md` §5](../operations/COMPLIANCE_POSTURE.md) already uses
for the legal layer, applied to the enforcement layer: **establishes / does not
establish / left to the operator**.

Nothing here is forward-looking. Every "establishes" claim is backed by code or
an ADR, and anything not shipped appears only in the middle column.

**Reviewed against 2.24.0.** Every claim below was re-checked against the code
that release ships. What moved since the 2.22.0 review is the **audit** side: a
refused call now leaves an audit record of its own (`ToolCallRefused`, exported
as a `denied` tool invocation), a group call's record names the group, an
allowed call's record names the role that admitted it, and the front door's
flat `tools/call` now checks `tool:invoke`. Spans gained the L7 verdict and lost
the caller's own ids by default. Rows corrected for it: the listed digest (new),
approval `approved`, L7 Enforce, L7 Audit, any L7 verdict, the `Mcp-Param-*` selector, tool
access and auth -- see
[what a refusal leaves since 2.24.0](#what-a-refusal-leaves-since-2240). The
tool access row also named the wrong log line for a front-door denial, a slip
present since 2.22.0.
A record is only as good as the gateway that wrote it: read
[what a record from before 2.24.0 lacks](#what-a-record-from-before-2240-lacks)
before trusting an export a 2.23.x or earlier gateway produced, and
[the three rows that were weaker before 2.16.0](#three-rows-that-were-weaker-before-2160)
before reading anything a 2.15.0 or earlier gateway produced.

## The table

| Verdict | Establishes | Does not establish | Operator's side |
| --- | --- | --- | --- |
| **Digest pin passed** | the tool's `{name, description, inputSchema, outputSchema}` is byte-identical (RFC 8785 JCS) to the pinned one | the tool is safe; that `annotations`, `execution`, `icons` or `_meta` are unchanged; that the upstream *implements* the schema it declares; **that an empty-valued field is unchanged** — `None` / `""` / `{}` / `[]` are dropped before canonicalization (`digest_computation._is_meaningful`), so gaining `description: ""` or losing `outputSchema` to `{}` moves nothing | pin provenance: since 2.18.0 `mcp-hangar pin --write` records what a server served at a moment nobody else witnessed, so *who ran it, and against which upstream* is the operator's to keep; who approved the digest |
| **`pin --check` clean** *(2.18.0)* | at the moment the command ran, every tool named in `tool_projection.pins` was served with the digest the file records — computed by `compute_tool_digest`, the same function the gate compares against, so a clean check and a passing call agree by construction rather than by two implementations | that it still holds: an upstream can change between the check and the call, which is what the gate is for; anything about a tool that is served and **not** pinned — `pins` is a subset by design and an unpinned tool is not drift; that the servers behave as their schemas say | which tools are pinned at all; running the check where it can fail loudly (exit 1) rather than only before a release |
| **Digest mismatch / unknown** | the contract moved, or was never pinned; the record carries expected, observed, `enforcement`, `correlation_id`, `tenant_id` | that the change is hostile; whether the caller was served or refused — read `enforcement`, where `DigestEnforcement.BLOCK` is the only blocking value | `block` vs `warn`; the `unknown` policy (`ALLOW_UNVERIFIED` returns valid and emits no event at all) |
| **Listed `digest` / `pinned_digest`** *(2.24.0)* | the tool as this listing returned it hashes to `digest` under `compute_tool_digest`, the function `pin` and the gate use; `pinned_digest`, when present, is the pin found for the id the caller named, then for the group member that served the listing -- on `hangar_tools` for the caller's tenant or all tenants, on `GET /api/tools` and `GET /api/mcp_servers/{id}/tools` the all-tenants pin only. A pair that differs is drift, read without the CLI | that a call will be refused or served -- the gate decides at call time, and the upstream can change between the listing and the call; that the upstream serves this schema when the server has predefined tools -- the listing, and so the digest, is the schema the configuration declares; **that a missing `pinned_digest` means no pin** -- a pin a member inherits from a group that owns it is not shown, and a per-tenant pin is not shown on the REST routes; anything about a tool the caller cannot list, which carries neither field | reading `pinned_digest` against `tool_projection.pins`, the file that is the pin's source |
| **Approval `approved`** | one principal (`decided_by`) resolved this `approval_id` before `expires_at`; at dispatch the state, the expiry and a hash of the **raw** arguments were re-checked (`ApprovalGateService.revalidate`) | that the approver saw the raw arguments — they saw a redacted copy; that the approver was competent or authorized in any legal sense; that the call was dispatched — an approval that arrives after the batch's deadline has passed reads `CancellationError` and is not dispatched; that the call then succeeded | who may resolve; channel delivery; hold timeout |
| **Approval `expired` / `denied`** | the call was not dispatched through this gate | anything about whether it was attempted elsewhere | — |
| **L7 egress `deny` (Enforce)** | the call was refused before reaching the upstream, and the refusal is recorded: `EgressPolicyEnforced` carries tool, server, `action`, reasons, `rule_kind`, `policy_id`, `correlation_id`, `identity_context`; `mcp_hangar_egress_policy_enforced_total{action,rule_kind}` counts it; a `batch_call_refused` warning carries the verdict as bounded fields (`l7_verdict`, `l7_mode`, `l7_rule_kind`, `l7_inspection_failed`, `policy_id`) rather than the reasons, since 2.24.0; and since 2.24.0 the call has an audit record, `ToolCallRefused`, with `hangar.l7.verdict`, `hangar.l7.mode`, `hangar.l7.rule_kind` and `hangar.l7.policy_id` | that traffic did not reach the destination by another path; that established connections were cut — they are not (conntrack, see [EGRESS_POLICY](../guides/EGRESS_POLICY.md)); the reasons — they are on the event and the aggregate's `egress_policy_enforced` warning only, never on a span, the `batch_call_refused` line or the audit record. A deny because the arguments **could not be inspected** (`rule_kind` `arguments`) is still refused and still in `EgressPolicyEnforced`, but reads as a failure everywhere else: `batch_call_failed` at warning, a span that ends ERROR with `hangar.call.outcome=error`, and no `ToolCallRefused` | backstop flavour; pod restart after switching to `Enforce` |
| **L7 `deny` observed (Audit)** | the policy *would* have refused: `EgressPolicyViolationObserved` carries the same fields, with `would_be_action` in place of `action` and no `rule_kind`, and `mcp_hangar_egress_policy_violations_observed_total` counts it; since 2.24.0 the call's span reads `hangar.l7.verdict=audit_observed` | that anything was blocked — Audit falls through and the call proceeds | the decision to switch to `Enforce` |
| **Any L7 verdict** | which policy produced it: `policy_id` is a content hash of the compiled rules, carried by the verdict, by the refusals and by `EgressPolicySet` -- and since 2.24.0 by the call's span (`hangar.l7.policy_id`) and a refusal's audit record -- so a record and a policy change join on a value rather than on adjacent timestamps | that the *rules* are visible in the record — the id resolves to them only against a gateway still holding that policy (`GET /api/mcp_servers/{id}/l7_policy` returns `policyId`) | keeping the policy documents that ids were computed from |
| **L7 verdict by `Mcp-Param-*` selector** | the header matched a rule **and** the header was validated against the request body: only the front door binds a header for the policy, only one the called tool declares with `x-mcp-header`, only after re-running the SDK's check, and as the SDK decoded it (a `=?base64?...?=` sentinel included) | anything on a request where a header was not checked — `hangar_call` (it declares no header), a handshake-era request, a skipped or failed validation, a state that does not say validation ran: none of these headers reaches a selector, and the call falls through to the tool rules and the policy default ([ADR-025](../adr/ADR-025-header-selectors-must-not-match-unvalidated-headers.md)); the fall-through is visible as `rule_kind` `tool` and in the verdict reasons ("header rules not consulted", on the event), not in the absence of one. A checked header beside an unchecked one still decides, with that reason added | `headers.param_validation.required`, which refuses a modern-revision call carrying an `Mcp-Param-*` header that did not reach the selector rather than serving it; a handshake-era call is served with its headers ignored |
| **Tool access `denied`** | this caller cannot call this tool | that the tool does not exist — **at the front door**, withdrawn, denied and unknown are all `-32601`, deliberately (shown equals callable, [ADR-022](../adr/ADR-022-the-management-surface-is-what-the-caller-may-call.md)). On the batch surface the answer differs: `ToolAccessDeniedError`, "Tool not available for this mcp_server". **A front-door denial leaves no audit record**: it is answered before the executor runs, so there is no `ToolCallRefused` and no `batch_call_refused` for it | reading the operator-side log, which carries the reason the client is not given. At the front door that is `front_door_tool_call` at info with `outcome=not_found` and `reason=not_projected` (`unknown` when no upstream holds the name). On the batch surface — and at the front door for a tool denied between the listing and the call — it is `batch_call_refused` at warning, carrying `gate=tool_access` and `reason=tool_not_in_access_policy` (the per-gate `tool_access_denied` line is still written, at debug), and since 2.24.0 a `ToolCallRefused` audit record with the same gate and reason |
| **Empty projection (`{"tools": []}`)** | nothing about whether the caller is allowed anything | which of `no_identity` (a fail-closed deny), `nothing_discovered` (a replica whose warm-up has not finished or did not succeed) or `filtered` (the honest empty) produced it — indistinguishable from outside, classified only on the operator's side: in the log line and in the `reason` label of `mcp_hangar_empty_projection_total` | reading that log line before treating `[]` as a policy result |
| **SSRF check passed** | the endpoint resolved to a permitted range at registration and, for an API-registered `remote` server, again at connect — `_SsrfGuardedTransport` re-resolves and pins per request | anything about `remote` endpoints declared in `config.yaml` ([ADR-021](../adr/ADR-021-config-file-endpoints-outside-the-ssrf-policy.md)) — the boot warning names each one, a hostname included (`ssrf_policy_not_applied_to_config_file_endpoint`), but it warns and does not refuse | knowing that moving an upstream into the config file drops both halves |
| **Auth `401` / `403`, `tool:invoke` denied** | the credential was not accepted, or the principal lacks the permission. A `tool:invoke` denial of a tool call is not an HTTP status: it is `Not authorized to invoke tool '<tool>': tool:invoke permission required` — a failed batch entry (`AuthorizationDenied`) on `hangar_call`, and since 2.24.0 a tool error (`isError`) on the front door's flat `tools/call` — and since 2.24.0 one `ToolCallRefused` with `gate=authorization` and reason `tool_invoke_denied` or `unauthenticated`. An allowed call's audit record carries `mcp.caller.roles` *(2.24.0)*: the role the allow decision matched, or `opa_policy` | over stdio, that anyone presented a credential — the principal is the one `auth.stdio.principal` declares, trusted because the process was spawned ([ADR-026](../adr/ADR-026-stdio-is-an-authenticated-transport.md)); what the matched role grants, or granted when the call was made; any role on a trace — `mcp.caller.roles` is on the audit record only, and absent with auth off | role mapping; the stdio declaration |
| **Capability drift** | `CapabilityViolationDetected` with `violation_type`, `violation_detail` and the `enforcement_action` taken (`alert` / `block` / `quarantine`) | that the drift was hostile | which action the mode maps to |
| **Projection withdrawal** | a tool was withheld, and why: `mcp_hangar_projection_withdrawals_total{reason}` — `invalid_x_mcp_header` or `header_exposure_withdraw` | that the upstream stopped offering it — the definition is still served byte-identical upstream, only the projection dropped it; that a `header_exposure_warn` sample was withheld — `warn` counts the tool and still serves it | `on_violation`, whose default `warn` serves the tool |

## What a refusal looks like since 2.22.0

Nothing a verdict *establishes* changed here. What changed is where the record
is, which matters to anyone holding an export or a saved query.

**One line per refusal.** Every gate that refuses a call now logs
`batch_call_refused` at warning, carrying the `gate` that refused and its bounded
`reason`
([mcp-hangar#1557](https://github.com/mcp-hangar/mcp-hangar/issues/1557)). Before
2.22.0 each gate wrote its own line under its own name -- `tool_access_denied`,
`tool_withdrawn_rejected`, `tool_digest_pin_rejected`,
`tool_digest_pin_unresolvable` -- at info. Those four are still written, at
debug, so a saved query keyed on one of them **silently returns nothing against a
2.22.0 gateway**, and against an earlier one `batch_call_refused` is absent for
everything except the two L7 refusals. 2.24.0 narrowed the line again -- see
below.

**A refusal is no longer an error trace.** The span a refused call leaves ends
UNSET rather than ERROR, and carries `hangar.call.outcome=deny`,
`hangar.refusal.gate` and `hangar.refusal.reason`
([mcp-hangar#1556](https://github.com/mcp-hangar/mcp-hangar/issues/1556)). So
**counting ERROR spans no longer counts refusals**, in either direction: an
export from 2.21.x or earlier has refusals mixed into its error traces, and one
from 2.22.0 does not. The bounded `error.type` still names what refused on both.
One exception since 2.24.0: an L7 deny because the arguments could not be
inspected ends ERROR, with `hangar.call.outcome=error`, because the evaluator
broke.

## What a refusal leaves since 2.24.0

**An audit record.** A refused call now publishes one `ToolCallRefused`
([mcp-hangar#1619](https://github.com/mcp-hangar/mcp-hangar/pull/1619)): a batch
gate that says `deny` (the tenant budget included, when its slot is taken after
the gates), a `tool:invoke` denial (`gate=authorization`), and an L7 `deny` or
`require_approval` at dispatch. The OTLP audit exporter writes it as
`tool_invocation` with `mcp.tool.status=denied`, the caller and tenant fields,
and `hangar.gate.name` and `hangar.gate.reason`, or the `hangar.l7.*` fields;
CEF, LEEF, JSON lines and syslog write it as `ToolInvocationDenied` (event id
`103` in CEF, LEEF and syslog).
It carries codes only, never the refusal's text. Three things it does **not**
establish, all of the same form -- the absence of a record:

- **Not every refusal has one.** A front-door `-32601`, a suspended session and
  a refused `Mcp-Param-*` header are answered before the executor runs, a gate
  that broke rather than refused is not a refusal, and an inspection-failed L7
  deny is not either. On the front door, its `front_door_tool_call` line is the
  record of the first three.
- **The publish is best-effort.** One that fails is logged as
  `tool_call_refused_not_published` and the call is still refused.
- **Both exports are opt-in.** The OTLP audit record is written only when an
  OTLP endpoint is set explicitly (`OTEL_EXPORTER_OTLP_ENDPOINT` or
  `observability.tracing.otlp_endpoint`) and `MCP_AUDIT_EXPORT_ENABLED` has not
  turned it off; the compliance formats only when `MCP_COMPLIANCE_FORMAT` is
  set.

**A group call's record names the group.** `mcp.server.id` on a
`tool_invocation` record is the target the caller named, and the member that
served it is `hangar.route.backend`
([mcp-hangar#1620](https://github.com/mcp-hangar/mcp-hangar/pull/1620)) -- the
names spans use. A record persisted before the change replays with the member in
both.

**Roles are on the record, not the trace.** `mcp.caller.roles` is the role the
`tool:invoke` decision matched
([mcp-hangar#1621](https://github.com/mcp-hangar/mcp-hangar/pull/1621)), and no
code path can put it on a span
([mcp-hangar#1630](https://github.com/mcp-hangar/mcp-hangar/pull/1630)). Spans
also stopped carrying the caller's user, agent and session ids by default
([mcp-hangar#1584](https://github.com/mcp-hangar/mcp-hangar/pull/1584)): they
are set only with `observability.tracing.caller_ids: true` or
`MCP_TRACING_CALLER_IDS=true`. So **a 2.24.0 trace does not say who called**
unless the operator opted in; the audit record does.

**The log line carries no gate's text.** A gate refusal's `batch_call_refused`
lost its `error` field, the message the caller is told, which some gates fill
with text they do not bound
([mcp-hangar#1589](https://github.com/mcp-hangar/mcp-hangar/pull/1589)); an L7
refusal's line keeps `error`, the fixed caller-facing message, and carries the
verdict's bounded fields in place of the policy's reasons ([mcp-hangar#1596](https://github.com/mcp-hangar/mcp-hangar/pull/1596));
and a tenant-budget refusal after the gates is now logged at all, as
`gate=tenant_budget`
([mcp-hangar#1632](https://github.com/mcp-hangar/mcp-hangar/pull/1632)). A call
that reaches its gates after the batch's budget ran out reads `batch_timeout`
from the `global_timeout` gate every time; before, it could read `cancelled`
depending on thread timing
([mcp-hangar#1591](https://github.com/mcp-hangar/mcp-hangar/pull/1591)).

**The trace shows the L7 verdict and the route.** `batch.call.<tool>` carries
`hangar.l7.verdict` (`allow`, `audit_observed`, `deny`, `require_approval`,
`approval_honored`) with the mode, rule kind and policy id, and the route:
`hangar.route.backend`, the member a group call went to, and
`hangar.route.reason`
([mcp-hangar#1595](https://github.com/mcp-hangar/mcp-hangar/pull/1595)). An L7
refusal is marked `hangar.call.outcome=deny` with those fields, not with
`hangar.refusal.gate`, which names a batch gate.

## What a record from before 2.24.0 lacks

The same rule as the next section: a record does not improve when the code
does. An export from a 2.23.x or earlier gateway has the older behaviour.

**A refusal is in no audit export.** The OTLP audit exporter and the compliance
formats wrote successes and upstream failures only. A refusal appeared in the
log and, for some, as a domain event of its own -- `EgressPolicyEnforced`,
`ToolApprovalDenied`, `AuthorizationDenied` -- which neither exported. Its
absence from an export is not evidence that nothing was refused.

**A group call's record names the member**, not the group, and **no record names
a role**: `mcp.caller.roles` was defined and never written.

**A front-door call did not establish `tool:invoke`.** The flat `tools/call`
never checked it, so with auth on a principal without it -- one holding only
`viewer`, for example -- was served what `hangar_call` refused it
([mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623)).

**A header verdict on `hangar_call` did not establish validation.** Every
`Mcp-Param-*` header on a modern request was handed to the policy as validated,
including on `hangar_call`, where nothing checks it against the body, and a
header mapping that did not state validation was read as validated
([mcp-hangar#1598](https://github.com/mcp-hangar/mcp-hangar/pull/1598),
[mcp-hangar#1601](https://github.com/mcp-hangar/mcp-hangar/pull/1601)). An
earlier gateway's `rule_kind=header` verdict on `hangar_call` says a header
matched, and nothing about whether the header was true.

**Spans carried the caller's ids by default** -- `mcp.caller.id`, `mcp.user.id`,
`mcp.agent.id` and `mcp.session.id` on every authenticated call -- and **no span
named the L7 verdict or the member a group call went to**.

## Three rows that were weaker before 2.16.0

This page was drafted against 2.15.0, where three of its rows read worse. They
are kept here because a record does not improve when the code does: anyone
holding an export from a 2.15.0 or earlier gateway -- or still running one --
has the older behaviour, whatever this page says about the current release.

**An enforced deny left almost no record.** Audit mode — the mode that by
definition changes nothing — emitted an event, a warning and a metric, while
Enforce mode emitted a `debug`-level line carrying the generic caller-facing
message, with the reason the policy computed left in `.details` where only the
REST middleware looked. Fixed in
[mcp-hangar#1128](https://github.com/mcp-hangar/mcp-hangar/pull/1136): a refusal
now publishes `EgressPolicyEnforced`, increments its own counter and logs at
warning, **since 2.16.0**. **A refusal by an earlier gateway is in no event
stream at all** — its absence from an export is not evidence that nothing was
refused.

**No verdict named its policy.** `PolicyEvaluationResult.policy_id` was
documented as "the policy that made the decision (for audit)" and was never set
by anything; the nearest answer was a timestamp join against `EgressPolicySet`,
which is a reconstruction rather than a record. Fixed in
[mcp-hangar#1129](https://github.com/mcp-hangar/mcp-hangar/pull/1135), released
in 2.16.0: every L7 verdict carries a content hash of the rules that produced it,
and the unfilled field is gone. **A verdict from an earlier gateway names no
policy**, and the timestamp join is the only reconstruction available for it.

**The approval copy leaked a nested secret.** Argument redaction matched
sensitive key names at the top level only, so `{"config": {"password": …}}` — and
the same key inside a list of records — was persisted and served verbatim to
every `approval:read` holder. Fixed in
[mcp-hangar#1130](https://github.com/mcp-hangar/mcp-hangar/pull/1134), released
in 2.16.0. **An approval record written by an earlier gateway may contain a
secret**, and the integrity hash is unaffected either way: it is computed over
the raw arguments by design.

## How to read a record you did not produce

1. **Find the reason, not only the outcome.** Every verdict above carries one.
   A record with an outcome and no reason is a log line, not a verdict.
2. **Find the rule.** For an L7 verdict that is `policy_id`; for a digest verdict
   the pinned digest; for tool access the policy scope in the operator-side log.
3. **Read the middle column before concluding anything.** Most of the wrong
   conclusions available here are of the form "it did not happen because I have
   no record of it" — and the middle column is where this page says which records
   do not exist.

## References

- [ADR-013 — egress policy enforcement model](../adr/ADR-013-egress-policy-enforcement-model.md)
- [ADR-025 — a header selector must not match an unvalidated header](../adr/ADR-025-header-selectors-must-not-match-unvalidated-headers.md)
- [operations/COMPLIANCE_POSTURE.md](../operations/COMPLIANCE_POSTURE.md) — the same shape at the certification layer
- [operations/COMPLIANCE.md](../operations/COMPLIANCE.md) — SIEM export formats
- [security/OWASP_MCP_TOP_10_COVERAGE.md](./OWASP_MCP_TOP_10_COVERAGE.md) — the same controls, per OWASP category
