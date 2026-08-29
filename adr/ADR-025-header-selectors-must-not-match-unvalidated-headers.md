# ADR-025: A Header Selector Must Not Match a Header Nobody Validated

**Status:** Proposed
**Date:** 2026-08-29
**Authors:** MCP Hangar Team

## Context

SEP-2243 lets a tool annotate an `inputSchema` property with `x-mcp-header`, so a
conforming client sends that argument's value as an HTTP header instead of in the body.
The point of the mechanism is that an intermediary can route on the header without
parsing the request. The safety property that makes it usable is **header-body
agreement**: the header must carry the same value the call will execute with, so nobody
can route on one value and execute another. The spec puts the obligation on the
intermediary, not on the client -- an intermediary enforcing policy on mirrored headers
must not treat them as trusted unless it knows they were checked.

The `mcp` SDK enforces that agreement pre-dispatch for `Mcp-Param-*` headers, and does
so **fail-open by design**. `_mcp_param_rejection` resolves the called tool's schema
through a nested `tools/list`, and `_tool_input_schema` returns `None` -- validation
skipped, dispatch continues -- when that listing raises, when it never advertises the
called tool, or when pagination does not terminate. A schema that does resolve can still
produce no rejection: `validate_mcp_param_headers` returns early when the tool's own
`x-mcp-header` annotations are invalid. The comment in the SDK is explicit that this is
deliberate: header validation must never break a working call path. On a legacy protocol
revision the ladder is not entered at all.

Two things changed on our side of that boundary in v2.14.0, and together they turn an
SDK design choice into a Hangar trust decision.

**We now route on these headers.** `MCPEgressPolicy` gained a
`headers.allow` / `deny` / `requireApproval` ladder that selects on `Mcp-Param-*`
(`mcp-hangar#1064`), and `routing_headers_var` carries the selectable headers to the
egress evaluator and the batch executor. Until then the honest statement was that Hangar
did not route or authorize on these headers, so the SEP's obligation was met by
construction and the risk belonged to whatever intermediary a deployment put in front of
us. That is no longer true: **we are that intermediary.**

**We can see the skip, and we count it.** `mcp_hangar_param_header_validation_skipped_total`
(`reason` = `listing_failed` | `tool_not_listed` | `invalid_annotation` | `legacy_protocol`)
was added in v2.15.0 (`mcp-hangar#1053`) so a skip is observable rather than silent.

What the selector gate does **not** know is the difference between those two facts.
`evaluate_headers` admits a request on protocol version alone:

```python
if headers is None or not is_modern_protocol_version(headers.get(PROTOCOL_VERSION_HEADER)):
    return None
```

The version says whether the headers *should have been* checked against the body. It
does not say whether they *were*. On a modern request where the nested listing raised,
the SDK skips validation, dispatch proceeds, and an `allow` / `deny` / `requireApproval`
selector then matches a header no component compared against the body. That is SEP-2243's
own failure mode -- route on one value, execute another -- relocated from a hypothetical
front-end proxy into Hangar's own policy engine.

The skip is neither one branch nor one function. `_tool_input_schema` has **five** exits
that return `None` -- an unresolved schema -- and `validate_mcp_param_headers`
(`shared/inbound.py`) adds one of its own, refusing to produce a rejection when the
tool's annotations are invalid; the caller treats both the same way, as "no rejection to
raise". A legacy revision skips the ladder without entering either. That is **seven**
ways a `tools/call` reaches dispatch with `Mcp-Param-*` headers nothing checked, and the
metric names four of them. They are not one class, and this matters because any remedy
addresses only some:

| Skip condition | Where | Metric reason | Is the call still executed? | Is it a routing gap? |
| --------------- | ------ | -------------- | ---------------------------- | --------------------- |
| Listing raised | `_tool_input_schema` | `listing_failed` | Yes -- dispatch continues | **Yes.** The only live one. |
| Listing exhausted without the tool | `_tool_input_schema` | `tool_not_listed` | No -- dispatch answers `-32601` | No, given the same-principal assertion (`mcp-hangar#1049`). An empty listing and a `-32601` are the same decision. |
| Tool's annotations invalid | `validate_mcp_param_headers` | `invalid_annotation` | Yes in the SDK; not reachable through Hangar | No -- but by our own projection, not by the SDK. See below. |
| Legacy revision (ladder not entered) | -- | `legacy_protocol` | Yes | Already handled: `#1064` refuses to match on a pre-validation revision. |
| Cursor cycle | `_tool_input_schema` | **none** | Yes -- dispatch continues | Would be, exactly as `listing_failed` is. Unreachable today: the front door returns one unpaged list and the projection never emits a `nextCursor`. |
| Pagination past the page cap | `_tool_input_schema` | **none** | Yes -- dispatch continues | Same. Unreachable for the same reason, and for as long as that stays true. |
| Envelope fails `tools/list` validation | `_tool_input_schema` | **none** | No -- dispatch rejects | No. A client fault; out of scope (Decision 4). |

The annotation row is two independent mechanisms that happen to agree, and it is worth
keeping them apart. **The SDK's** is a skip: given an invalid schema,
`validate_mcp_param_headers` returns no rejection and the call proceeds unvalidated --
the same fail-open posture as the rest of the ladder. **Hangar's** is a withdrawal:
since `mcp-hangar#1063` a governed tool whose `x-mcp-header` annotations are invalid is
withheld from the projection entirely, so it is absent from `tools/list` and `-32601` on
the call, and the SDK's skip has nothing to skip on. The two are not layers of one
control -- ours makes theirs moot for governed tools, and only for as long as the
withdrawal holds. What remains behind it is a `hangar_*` management tool with an invalid
annotation, and no management schema declares `x-mcp-header` at all. Hangar's own
`_observe_param_header_skips` re-checks the annotation for that residue, which is why
the metric still has the label: the counter mirrors the SDK's condition, while the
projection removes the population it could apply to.
So the decision this ADR records is narrow in mechanism and broad in principle: one
branch (a failed pre-dispatch listing on a modern request) is the live gap, and the
principle that closes it is the one `evaluate_headers` already applies to the legacy era.
The two pagination exits are the same class of gap held shut by an unrelated property of
our projection rather than by any decision, and they have no metric label -- so the first
change that paginates the front-door listing opens a skip nothing counts and nothing
sees. The annotation case is shut the same way: by a projection rule, not by the SDK
arm the metric is named after.

## Decision

### 1. A skipped validation is a non-match, not a trusted match

A header selector does **not** match on a request whose `Mcp-Param-*` validation did not
run. The request falls through to the tool-name rules and the policy default, exactly as
a handshake-era request already does.

This is the same argument `evaluate_headers` makes today for the legacy revision,
applied to the fact rather than to its proxy: what disqualifies a header is that nothing
checked it, and the protocol version was only ever a stand-in for that. Refusing to
match is the honest shape -- the request is not handed an `allow` it did not earn, nor a
`deny` some other caller's header wrote.

This is the **default**, and it needs no flag. A deployment that writes no `headers.*`
selectors cannot observe it; a deployment that does write them asked for enforcement on
a value it believes agrees with the body, and this is what makes that belief true.

Mechanically it requires the skip status to reach the evaluator. `routing_headers_var`
carries the selectable headers and the protocol version today; it must also carry
whether validation ran. The version check in `evaluate_headers` is then subsumed:
`legacy_protocol` is a skip like any other.

**The carrier is `request.state`, not a contextvar.** The skip is observed in the
listing path (the `except` in `_list_projected_tools`, which counts and re-raises), and
the evaluator reads a contextvar that `bind_routing_headers` **rebuilds from the raw
request headers rather than merging into**. A flag set as a contextvar out in the
listing would therefore be overwritten by the later bind. It happens to survive on the
modern path today -- the nested listing is awaited inline and a child task copies the
context -- but `bind_routing_headers`' own docstring exists because the SDK runs inbound
messages in decoupled tasks, and an implementation that leans on inline execution here
is one refactor away from a silent race. The per-POST channel that is already correct
for exactly this is `request.state`, where `mcp-hangar#1049` keeps the projection memo:
the `except` block sets `param_validation_ran = False` there, and
`bind_routing_headers` reads it when it builds the mapping.

**A non-match caused by a skip is recorded as such.** In the audit record and the
decision reason, "no rule matched" and "the rules were not consulted because nothing
validated the headers" are different verdicts. A selector that silently stops matching
is otherwise harder to debug than a refusal, and the skip metric alone cannot tell an
operator which request it happened on.

### 2. Refusing the call is a separate, opt-in control

`headers.param_validation.required: true` refuses a `tools/call` whose `Mcp-Param-*`
headers could not be validated, rather than serving it unvalidated.

This is deliberately a second, weaker-default control, because it has a blast radius
Decision 1 does not: it turns an upstream listing failure into a client-visible refusal
for every call carrying header parameters, whether or not a policy selects on them. An
operator who would rather serve a call than fail it keeps today's behavior; an operator
for whom an unvalidated header is not servable turns it on.

The flag is **global to the front door**, not per-server. The condition it reacts to --
a failed pre-dispatch listing -- is a property of the request, not of the upstream the
call would reach, so it does not belong beside the per-server `header_exposure:` block
even though the two govern the same SEP.

Only `listing_failed` reaches it. `tool_not_listed` is already a `-32601`, and
`legacy_protocol` is an era rather than a failure.

### 3. Reuse `HEADER_MISMATCH` (-32020), with a message that does not lie

The refusal in Decision 2 carries `HEADER_MISMATCH`, the code already used for
header-body disagreement, with a message stating the headers **could not be validated**.

The code is a slight overstatement: on a failed listing we do not know that the header
disagrees with the body, only that nobody could check. A third error code for one
class -- "your headers are not trustworthy here" -- would be worse for a client than a
single code with an accurate message, so the reuse is chosen deliberately rather than by
default.

One shape difference is worth recording, because it will surface in a client that
handles both: the SDK's own `Mcp-Param-*` refusal is pre-dispatch and arrives as a plain
`application/json` HTTP 400, while Hangar's refusal originates inside the request handler
and arrives as a JSON-RPC error on a 200. Same class, two shapes on the wire.

### 4. The skip signal mirrors a specific SDK version, and is pinned like one

`_call_carries_param_check` re-implements the SDK's own precondition -- no arguments and
no `Mcp-Param-*` headers means no validation was owed -- so that a skip is only counted
when a check was actually due. That is a copy of another project's control flow, true
for `mcp==2.0.0` and unverified for anything else. An SDK bump that moves the ladder does
not break the build; it makes the metric, and now the selector gate, quietly wrong.

The `Mcp-Param-*` ladder therefore joins the pin-tracked surfaces governed by
[ADR-012](ADR-012-interceptor-sep-pin-tracking-policy.md): an `mcp` upgrade re-diffs
`_tool_input_schema` / `_mcp_param_rejection` against the mirrored branches, and the
re-diff is part of the upgrade, not a follow-up.

The re-diff is against **every** skip condition in the table, in both functions --
including the two, cursor cycle and page cap, that Hangar cannot reach today and
therefore does not label. A mirror of four conditions out of seven passes its own
re-diff green while the SDK changes one of the three nobody mirrors, which is the
failure the pin is supposed to prevent. Two
consequences follow: the pagination exits are named in the re-diff checklist even while
unreachable, and any change that makes the front-door listing paginate must add their
reason labels **before** it lands -- otherwise it opens a skip that Decision 1 cannot
see and the metric does not count.

Explicitly out of scope: the SDK arm where the envelope itself fails `tools/list`
validation. That is a client fault which dispatch rejects on its own, and Hangar does not
mirror it.

### Activation

Decision 1 ships **on** -- it is a default, and the flag in Decision 2 is not its
gate. Decision 2 ships **off**; enabling it is a per-deployment choice, documented
beside the other activation switches.

Neither is retroactive to a release already cut: `mcp-hangar#1053` records that the skip
metric landed in v2.15.0 while the selector gate was still version-only, so a deployment
on v2.15.0 with `headers.*` selectors is inside the window this ADR closes.

## Consequences

### Positive

- The property SEP-2243 asks an intermediary to guarantee is guaranteed by the code path
  that does the routing, not by a premise about our feature set that a release can
  invalidate -- as v2.14.0 invalidated it.
- The fail-open boundary is named and located. An operator can say which side of it a
  given verdict came from, which is the minimum an enforcement plane owes a verdict.
- Refuse-to-match degrades toward the policy default, so closing the gap does not require
  anyone to accept new refusals. The refusing behavior exists, but only for operators who
  ask for it.
- One rule replaces the version check, so there is one place where "was this header
  checked?" is answered, rather than a version proxy in the evaluator and a metric
  elsewhere.

### Negative

- A selector can stop matching for a reason the policy author did not write, which is
  harder to reason about than a refusal. The distinct audit verdict required by
  Decision 1 and the skip metric are the compensating signals; without both, the
  behaviour reads as a policy that quietly does not work.
- We are now coupled to a specific SDK's internal control flow in two places (the metric
  and the gate) rather than one. Decision 4 makes that coupling a tracked pin rather than
  a latent assumption, but it does not remove it.
- `HEADER_MISMATCH` becomes slightly less precise: two conditions, one code, distinguished
  only by message.
- An operator who sets `required: true` converts an upstream availability problem into a
  client-visible refusal. That is the intended trade, and it is the reason the control is
  opt-in.

### Neutral

- Deployments without `headers.*` selectors and without the flag observe no change in
  behavior at all. Neither decision alters the synchronous call path for them.
- The projection-time controls this ADR sits next to are unchanged: invalid annotations
  still withdraw a tool, and `header_exposure` still governs what an upstream may oblige a
  client to expose.

## Alternatives Considered

### 1. Keep the version-only gate

- **Rejected**: the protocol version answers a different question from the one the gate
  needs answered. It reports the revision's obligation, not whether the obligation was
  discharged on this request, and the gap between the two is exactly the `listing_failed`
  branch.

### 2. Fail the call closed by default (no opt-in)

- **Rejected**: it converts any upstream listing failure into a client-visible refusal for
  every deployment, including those that never select on headers and are therefore not
  exposed to the problem. The routing risk is removed by Decision 1 without that cost.

### 3. Treat a skipped validation as an implicit `deny`

- **Rejected**: it lets one caller's unvalidated header produce a deny another caller's
  request never earned, which is the same defect as an unearned allow with the sign
  flipped. A non-match keeps the policy default in charge.

### 4. A third JSON-RPC error code for "could not validate"

- **Deferred**: cleaner in principle, but it splits one client-visible class in two and
  obliges every client to learn a Hangar-specific code. Revisit if the two conditions turn
  out to need different client handling in practice.

### 5. Wrap the SDK transport to observe the skip directly

- **Rejected**: it replaces a mirrored precondition with a fork of a dependency's request
  path -- a larger, quieter coupling than the one Decision 4 pins, and one an SDK bump
  breaks louder but no earlier.

### 6. Scrape the SDK's log lines instead of counting Hangar-side

- **Rejected**: some skip branches log and some do not, so the signal would be incomplete
  by construction, and log text is not an interface.

## References

- SEP-2243 (`Mcp-Param-*` header parameters and header-body agreement).
- Decision issue: `mcp-hangar#1053` (fail-open boundary; the skip metric shipped in
  v2.15.0). ADR issue: `docs#269`.
- The reason this matters now: `mcp-hangar#1064` (header selectors on `MCPEgressPolicy`,
  v2.14.0), `mcp-hangar#1063` (invalid annotations withdraw the tool),
  `mcp-hangar#1049` (per-request projection memo and the same-principal assertion),
  epic `mcp-hangar#1054` with `#1056` / `#1057` (SEP-2243 header governance).
- Implementation: `src/mcp_hangar/domain/policies/egress_l7.py` (`evaluate_headers`),
  `src/mcp_hangar/context.py` (`routing_headers_var`, `select_routing_headers`),
  `src/mcp_hangar/fastmcp_server/flat_tool_projection.py`
  (`_observe_param_header_skips`, `_observe_legacy_param_skip`, `_call_carries_param_check`),
  `src/mcp_hangar/metrics.py` (`PARAM_HEADER_VALIDATION_SKIPPED_TOTAL`).
- Upstream mirrored surface: `mcp/server/_streamable_http_modern.py`
  (`_tool_input_schema`, `_mcp_param_rejection`) at `mcp==2.0.0`.
- Related decisions: [ADR-012](ADR-012-interceptor-sep-pin-tracking-policy.md)
  (upstream pin tracking -- Decision 4),
  [ADR-013](ADR-013-egress-policy-enforcement-model.md) (egress policy enforcement model),
  [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
  (shown equals callable, the invariant the projection-side controls preserve).
- Operator guide: [Front-Door Mode](../guides/FRONT_DOOR.md), section
  "Header Exposure (`x-mcp-header`)".
