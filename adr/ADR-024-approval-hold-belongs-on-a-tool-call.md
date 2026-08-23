# ADR-024: A Human Approval Hold Belongs on a Tool Call, Not on a Fetch

**Status:** Accepted
**Date:** 2026-08-23
**Authors:** MCP Hangar Team

## Context

2.13.0 put prompts and resources on the same policy surface as tools: one `ToolAccessPolicy`, re-keyed `(mcp_server, kind, name)`, rather than parallel policy objects that could drift. The release notes and the loader's own docstring said the two new kinds inherit everything tools have, "the approval gate" included.

They did not. `ToolAccessPolicy.requires_approval()` has exactly one decision consumer, the tool call path in `BatchExecutor`; the prompts proxy and the resources projection contain no reference to approvals at all. An `approval_list` written under `access.prompt` or `access.resource` was therefore inert at request time -- the item was listed and served immediately, with no hold, no notification and no metric -- while the startup reachability check read the same key kind-blind and refused the boot over it. One configuration, fail-open at request time and fail-closed at boot.

The immediate defects are fixed: the key is refused where it is written, and the startup check asks about the kind it can enforce. What that fix cannot decide by itself is whether the refusal is permanent. Wiring `ApprovalGateService` into `prompts/get` and `resources/read` is a small change -- the policy object already answers `requires_approval()` for any name, and both surfaces already share the allow/deny decision through one function. The question is whether it should be made, and it is worth deciding once, in writing, because the shape of the approval record and the protocol conversation around it both depend on the answer.

There is a real counterweight, and stating it fairly is the point of this record. A fetch already carries a mandated human decision in this codebase: `resources/read` calls `UiResourceGuard.enforce()`, which for a `ui://` resource (MCP Apps, SEP-1865) requires consent before delivery and denies fail-closed without it. So "a human decision has no place on a fetch" is not a position this architecture can honestly take. The question is narrower: whether an operator-declared, name-pattern-driven hold belongs there, in addition to the one the spec mandates.

## Decision

### 1. `approval_list` is tool-only, and the load-time refusal for other kinds is permanent

A configuration that declares `approval_list` under `access.prompt` or `access.resource` is refused when it is read, naming the key and the absent enforcement path. This is not a placeholder for unimplemented work; it is the answer.

Four reasons, in the order they bind:

**The caller model differs.** A tool call is made deliberately, one at a time, by an agent already inside a turn that can block on a verdict; the hold has a natural place to happen and a natural party to wait. A `resources/read` is routinely a prefetch -- a client hydrating a link it was handed, often several at once, often with no human watching. `approval_timeout_seconds` defaults to 300. What a client does with a five-minute `resources/read` is not something a gateway gets to decide on its behalf.

**The listing surfaces have no third answer.** `prompts/list` and `resources/list` return present or absent. "Present but held" has no representation, so an approval-listed item is either shown and then blocked on fetch -- a fetch that can hang for minutes, which is indistinguishable from a broken gateway -- or hidden, at which point `approval_list` means `deny_list` with extra steps and a worse failure mode.

**The fan-out is wrong.** The resources decision is taken in one function reached from three places: the catalogue build, the handed-out `resource_link` union, and the read path. A hold behind that function turns one listing of N resources into N human decisions, or forces the hold to be applied inconsistently across the three -- which is exactly the listing/fetch drift the single decision point exists to prevent.

**The record is tool-shaped, deliberately, and it is being proposed upstream that way.** `ApprovalRequest` carries `tool_name` and an `arguments_hash`; the wire form under `io.mcp-hangar/approval` ([ADR-017](ADR-017-approval-input-request-namespace.md)) names `mcpServer`, `tool` and `argumentsHash`, and exists to be contributed to the protocol conversation on approvals. A URI fetch has a URI and no arguments. Growing the record a kind now, before that conversation lands, forks our own proposal against itself for a capability nobody has asked for.

### 2. The one human decision that does belong on a fetch is the SEP-1865 `ui://` consent

It stays, and it stays narrow. It is justified by what is being delivered rather than by who declared a pattern: a `ui://` resource is rendered in a client webview, which is an execution and exfiltration surface, and the spec mandates consent for it. It is gated by an allowlist first, so consent can only ever be asked for a resource an operator has already named, and it is per-resource rather than per-listing.

That carve-out is the boundary. A future hold on a fetch surface has to argue from the same footing -- what is delivered makes it dangerous, and the spec says so -- not from an operator having written a glob.

### 3. `deny_list` is the answer to "do not hand this out"

For everything an operator actually wants when they reach for `approval_list` on a resource, `deny_list` already does it: the item is absent from every listing and the read answers exactly like a nonexistent one. That is a complete answer, available today, with no hold and no third state.

### 4. This decision is superseded, not stretched, if the protocol grows the primitive

The condition is specific: a standard method that can put a decision to a party **other than the connected caller**. `elicitation/create` is not that method -- it asks the client, and the client is precisely the party an approval gate exists not to trust ([ADR-017](ADR-017-approval-input-request-namespace.md)). If such a method lands, a new ADR supersedes this one rather than an `approval_list` branch being quietly widened.

## Consequences

### Positive

- **The refusal can be worded honestly.** "Not supported for this kind" is a complete statement with a reason behind it, rather than a placeholder that invites the next contributor to implement the missing half.
- **One approval record shape.** `ApprovalRequest`, its persistence, its REST surface and the wire form proposed upstream all keep describing the same thing: a tool invocation with hashed arguments.
- **The fetch surfaces keep their single decision point.** Listing and reading continue to answer from one function, which is what makes "not shown" and "not fetchable" the same fact.
- **No new way to hang a client.** The only thing that can pause a fetch is the `ui://` consent, on a resource an operator allowlisted.

### Negative

- **An operator who wants per-resource human review does not get it.** Their options are `deny_list` (absolute) or nothing. If that gap turns out to be real in practice, this ADR is the thing to revisit -- with the use case attached.
- **The two kinds are no longer symmetrical with tools.** "Prompts and resources work like tools" now has an exception that has to be documented everywhere the policy surface is described.
- **The `ui://` carve-out looks arbitrary from outside.** It is defensible only by reference to SEP-1865; a reader who does not know that spec sees one consent path on a fetch and a refusal for another.

### Neutral

- **The SEP-1865 apparatus is dormant.** No configuration surface populates `UiResourcePolicy`, and no `UiConsentGate` implementation is wired, so an allowlisted `ui://` resource is denied for want of a consent gate and every `ui://` resource is denied for want of an allowlist. The carve-out this ADR preserves is therefore currently a deny in both directions. Finishing it -- a config surface plus an adapter over the approval gate -- is tracked separately; the decision recorded here is what that work must implement, and the fail-closed default is correct in the meantime.
