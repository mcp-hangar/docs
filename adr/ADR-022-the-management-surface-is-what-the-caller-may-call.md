# ADR-022: The Management Surface Is Whatever the Caller Is Allowed to Call

**Status:** Accepted
**Date:** 2026-08-11
**Authors:** MCP Hangar Team
**Related:** [ADR-013](ADR-013-egress-policy-enforcement-model.md) (the enforcement plane), core#232 (flat front-door projection), core#596 (wired onto the shipped path), core#904 (this decision), core#909 (the authorization it depends on).

## Context

Hangar serves one of two tool surfaces, chosen by `tool_access.mode`:

* `egress`, the default -- `tools/list` returns the twenty-two `hangar_*` meta-tools and nothing else. Upstream tools are reached through `hangar_call`.
* `front_door` -- `tools/list` returns flat upstream tool names and the `hangar_*` surface disappears entirely, for everyone.

They are mutually exclusive; the handlers are swapped wholesale at bootstrap. So a deployment picks, once, per instance, and every caller on it gets the same answer.

That is the actual complaint behind the report that started this. An agent client behind a front door does not need the control plane in its prompt prefix, and an operator does need it -- and today satisfying both means running two instances. The report described it as over-projection of `hangar_*` alongside governed tools, measured at ~50k tokens. That is not what happens: the two surfaces never appear together, and the `egress` surface measures 40,496 bytes, roughly 10-13k tokens. The framing was wrong; the requirement under it was not.

A second finding decided the shape. Of the twenty-two tools, only `hangar_call` authorized anything (core#909). The others mutated the fleet for any authenticated caller, while the equivalent REST routes were permission-gated. Hiding a tool that anyone may still call by name is not a control, so any decision here had to sit on top of real authorization rather than instead of it.

## Decision

### 1. The default surface does not change

`egress` keeps serving `hangar_*`. It is not a management surface that happens to be visible -- it *is* the surface: without `hangar_call` a client in `egress` mode can reach no upstream tool at all. Removing the meta-tools from the default projection would leave an empty catalogue, which is why the "make it opt-in" framing does not survive contact with the code.

Nothing here is breaking.

### 2. In `front_door`, a caller sees the management tools it is authorized to call

The projection stops being a property of the instance and becomes a property of the caller. For each `hangar_*` tool, the same check that core#909 runs on invoke decides whether it appears: the tool's entry in `TOOL_PERMISSIONS`, evaluated against the caller's principal by the authorizer.

An agent principal holding `developer` sees the flat upstream tools and no control plane. An operator principal holding `provider-admin` sees the flat upstream tools plus the management tools that role permits. One instance, one endpoint, two different answers -- which is the criterion this decision was measured against.

### 3. Authorization decides, and the projection follows it

The alternatives were a configuration flag and a separate endpoint. Both were rejected, and for the same reason.

A flag is instance-wide, so it reproduces exactly the limitation being removed. A separate path -- `/mcp` and `/mcp/admin` -- makes the surface a function of the URL, which means the protection is that the client does not know the other address. That is not access control, and it doubles the transport and session wiring to obtain it.

Binding to authorization introduces no new vocabulary, no new role, and no second place where "who may manage this gateway" is written down. The listing cannot drift from the enforcement because it is the same table and the same authorizer.

### 4. The rule is: shown implies callable, and not shown implies not callable

A projection that hides a tool the caller could still invoke would be worse than no filter, because it reads as a control. The two directions are the same decision evaluated at two moments, so the invariant is that they agree.

`hangar_call` and the two continuation tools are excluded from this surface, as invoke path rather than control plane. On a front door the flat names are how a tool is called; `hangar_call` is the `egress` way in, and the continuation tools hand back the tail of a truncated *tool result*, which is the business of whoever made the call rather than of whoever administers the fleet. (A front-door client that receives a truncated result cannot currently fetch the rest -- the flat surface projects neither tool. That gap predates this decision and is not closed by it.)

## Consequences

**An operator can stop running two instances.** That was the point.

**`front_door` still requires authentication.** With no identity the resolver already denies every tool fail-closed, and now there is a second reason: with no principal there is nothing to authorize the management tools against. This is a precondition of the mode, not a new one.

**A caller with no permissions sees a smaller list than before.** In `front_door` that list was empty of `hangar_*` for everyone, so no caller loses anything it had.

**The split is exactly as narrow as the roles are.** This decision makes the surface follow authorization; it does not make the authorization finer. `provider-admin` holds `mcp_servers:read` and not `:lifecycle`, so an operator reads the fleet here and cannot start or stop a server -- which is what that role can and cannot do over REST, and the mirroring is the point. Less comfortably, none of the built-in roles is a good fit for an agent: `developer` holds read, write *and* lifecycle, so an agent given it sees fleet tools. That is already true of the REST API, and the answer is a role scoped to what an agent does -- `tool:invoke` and nothing else -- rather than a second filter here that would disagree with the enforcement.

**The projection costs an authorization decision per management tool per `tools/list`.** Twenty-two in-memory role lookups on a call that already walks the whole projection registry.

**`egress` is untouched, and still shows every caller the whole meta-API.** Narrowing it the same way is available and deliberately not taken here: it would change the default surface, and the deployments that want a per-caller surface are the ones that turn on `front_door`.
