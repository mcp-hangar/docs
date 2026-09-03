<!-- verified-against: 2.18.0 -->

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

**Reviewed against 2.18.0.** Every claim below was re-checked against the code
that release ships; the table did not move, and 2.18.0 adds one row rather than
correcting any. Three rows still read differently before **2.16.0**, and a record
is only as good as the gateway that wrote it: see
[the section below](#three-rows-that-were-weaker-before-2160) before reading
anything a 2.15.0 or earlier gateway produced.

## The table

| Verdict | Establishes | Does not establish | Operator's side |
| --- | --- | --- | --- |
| **Digest pin passed** | the tool's `{name, description, inputSchema, outputSchema}` is byte-identical (RFC 8785 JCS) to the pinned one | the tool is safe; that `annotations`, `execution`, `icons` or `_meta` are unchanged; that the upstream *implements* the schema it declares; **that an empty-valued field is unchanged** — `None` / `""` / `{}` / `[]` are dropped before canonicalization (`digest_computation._is_meaningful`), so gaining `description: ""` or losing `outputSchema` to `{}` moves nothing | pin provenance: since 2.18.0 `mcp-hangar pin --write` records what a server served at a moment nobody else witnessed, so *who ran it, and against which upstream* is the operator's to keep; who approved the digest |
| **`pin --check` clean** *(2.18.0)* | at the moment the command ran, every tool named in `tool_projection.pins` was served with the digest the file records — computed by `compute_tool_digest`, the same function the gate compares against, so a clean check and a passing call agree by construction rather than by two implementations | that it still holds: an upstream can change between the check and the call, which is what the gate is for; anything about a tool that is served and **not** pinned — `pins` is a subset by design and an unpinned tool is not drift; that the servers behave as their schemas say | which tools are pinned at all; running the check where it can fail loudly (exit 1) rather than only before a release |
| **Digest mismatch / unknown** | the contract moved, or was never pinned; the record carries expected, observed, `enforcement`, `correlation_id`, `tenant_id` | that the change is hostile; whether the caller was served or refused — read `enforcement`, where `DigestEnforcement.BLOCK` is the only blocking value | `block` vs `warn`; the `unknown` policy (`ALLOW_UNVERIFIED` returns valid and emits no event at all) |
| **Approval `approved`** | one principal (`decided_by`) resolved this `approval_id` before `expires_at`; at dispatch the state, the expiry and a hash of the **raw** arguments were re-checked (`ApprovalGateService.revalidate`) | that the approver saw the raw arguments — they saw a redacted copy; that the approver was competent or authorized in any legal sense; that the call then succeeded | who may resolve; channel delivery; hold timeout |
| **Approval `expired` / `denied`** | the call was not dispatched through this gate | anything about whether it was attempted elsewhere | — |
| **L7 egress `deny` (Enforce)** | the call was refused before reaching the upstream, and the refusal is recorded: `EgressPolicyEnforced` carries tool, server, `action`, reasons, `rule_kind`, `policy_id`, `correlation_id`, `identity_context`; `mcp_hangar_egress_policy_enforced_total{action,rule_kind}` counts it; a warning names the reason | that traffic did not reach the destination by another path; that established connections were cut — they are not (conntrack, see [EGRESS_POLICY](../guides/EGRESS_POLICY.md)) | backstop flavour; pod restart after switching to `Enforce` |
| **L7 `deny` observed (Audit)** | the policy *would* have refused: `EgressPolicyViolationObserved` carries the same fields, and `mcp_hangar_egress_policy_violations_observed_total` counts it | that anything was blocked — Audit falls through and the call proceeds | the decision to switch to `Enforce` |
| **Any L7 verdict** | which policy produced it: `policy_id` is a content hash of the compiled rules, carried by the verdict, by the refusals and by `EgressPolicySet`, so a record and a policy change join on a value rather than on adjacent timestamps | that the *rules* are visible in the record — the id resolves to them only against a gateway still holding that policy (`GET /api/mcp_servers/{id}/l7_policy` returns `policyId`) | keeping the policy documents that ids were computed from |
| **L7 verdict by `Mcp-Param-*` selector** | the header matched a rule **and** the header was validated against the request body | anything on a request where validation was skipped — such a request matches no selector at all and falls through to the tool rules and the policy default ([ADR-025](../adr/ADR-025-header-selectors-must-not-match-unvalidated-headers.md)); the fall-through is visible in the verdict reason, not in the absence of one | `headers.param_validation.required`, which refuses an unvalidated call rather than serving it |
| **Tool access `denied`** | this caller cannot call this tool | that the tool does not exist — **at the front door**, withdrawn, denied and unknown are all `-32601`, deliberately (shown equals callable, [ADR-022](../adr/ADR-022-the-management-surface-is-what-the-caller-may-call.md)). On the batch surface the answer differs: `ToolAccessDeniedError`, "Tool not available for this mcp_server" | reading the operator-side log, which carries the reason the client is not given |
| **Empty projection (`{"tools": []}`)** | nothing about whether the caller is allowed anything | which of `no_identity` (a fail-closed deny), `nothing_discovered` (a replica whose warm-up has not finished or did not succeed) or `filtered` (the honest empty) produced it — indistinguishable from outside, classified only in the operator-side log | reading that log line before treating `[]` as a policy result |
| **SSRF check passed** | the endpoint resolved to a permitted range at registration and, for an API-registered `remote` server, again at connect — `_SsrfGuardedTransport` re-resolves and pins per request | anything about `remote` endpoints declared in `config.yaml` ([ADR-021](../adr/ADR-021-config-file-endpoints-outside-the-ssrf-policy.md)) — and the boot warning does not enumerate them, because `endpoint_is_a_literal_the_strict_policy_refuses` answers `False` for **any** hostname, so a file-declared `http://internal.corp/mcp` is outside the policy and silent | knowing that moving an upstream into the config file drops both halves |
| **Auth `401` / `403`** | the credential was not accepted, or the principal lacks the permission | — | role mapping |
| **Capability drift** | `CapabilityViolationDetected` with `violation_type`, `violation_detail` and the `enforcement_action` taken (`alert` / `block` / `quarantine`) | that the drift was hostile | which action the mode maps to |
| **Projection withdrawal** | a tool was withheld, and why: `mcp_hangar_projection_withdrawals_total{reason}` — `invalid_x_mcp_header` or `header_exposure_<action>` | that the upstream stopped offering it — the definition is still served byte-identical upstream, only the projection dropped it | `on_violation`, whose default `warn` serves the tool |

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
