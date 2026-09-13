# ADR-028: On a Front Door, the Tool-Access Policy Is the Invoke Gate for Upstream Tools

**Status:** Proposed
**Date:** 2026-09-13
**Authors:** MCP Hangar Team

## Context

[ADR-027](ADR-027-egress-is-a-trust-mode-not-a-preset.md) recorded that the two
paths to an upstream tool authorize a call differently. Paths and line numbers
below are in the published `mcp-hangar` 2.19.1 wheel, relative to the
`mcp_hangar/` package.

**`hangar_call`** validates each call against the fleet, then runs
`_authorize_calls`, then hands the batch to `BatchExecutor`.

- **Validation.** It checks that the named server or group and the named tool
  exist, and it runs before any authorization (`server/tools/batch/__init__.py:490`).
- **`_authorize_calls`** is called at `:518`.
  - With auth off, it allows every call (`:131`-`:132`).
  - With auth on, it refuses the whole batch when the principal is missing or
    anonymous (`:144`). Otherwise it requires `tool:invoke` per call, with the
    bare tool name as the resource id, and fails closed (`:163`-`:189`).
  - `tests/live/test_t2_auth.py` pins this over HTTP: a `viewer` is refused and a
    `developer` is not.

**The flat front-door path** resolves the requested name against the caller's
flat map before anything else. That map is built by `_build_flat_map` from the
governed decision, `is_governed_allowed`, which applies the tool-access policy
and the withdrawal scopes with each group member collapsed into its group. It
also applies two header filters: `x-mcp-header` annotations must be valid, and
the operator's `header_exposure` block must allow the tool.

A name outside the map is `-32601`. A denied item is answered exactly like a
missing one, which keeps the front door from being a cross-tenant enumeration
oracle (`mcp-hangar#905`). A name inside the map dispatches through its group
(`fastmcp_server/flat_tool_projection.py:944`), and then `BatchExecutor` runs
its gates (`server/tools/batch/executor.py:1795`-`:1808`).

None of those steps checks an RBAC permission.

The two paths are served in different modes today, so no surface shows both.
`mcp-hangar#1370` changes that. Its default front-door surface is `hangar_find`
+ `hangar_call` + the management tools a caller is permitted, with
`tool_projection.flat` as the opt-in, so one front door would carry both rules.

An HTTP principal holding `viewer`, which lacks `tool:invoke`, could then call a
tool by its flat name and be refused the same tool through `hangar_call`. A
discovery tool that lists what the projection holds would show tools that
`hangar_call` then refuses. [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
set the rule that shown means callable for the management surface. The same
reasoning applies here.

On stdio, `tool:invoke` decides nothing today
([ADR-026](ADR-026-stdio-is-an-authenticated-transport.md)):

- With auth off, `_authorize_calls` allows every call.
- With auth on, it looks for the principal on an HTTP request that a pipe never
  carries, so it refuses a stdio caller as anonymous.

The split is therefore an HTTP concern.

Two properties of `tool:invoke` matter for what replaces it.

- **A grant is per tool name, not per server.** A permission names a resource id
  (`domain/value_objects/security.py:141`, matched at `:151`-`:166`), and
  `_authorize_calls` passes the bare tool name as that id. A grant therefore
  covers that name on every server, while the tool-access policy is keyed by
  server, group and tenant, never by principal.
- **Continuations are not bound by it.** `hangar_fetch_continuation` and
  `hangar_delete_continuation` hand back the tail of a truncated `hangar_call`
  result. They are gated by `tool:invoke` against every resource id, and they
  accept a grant held within any tenant
  (`server/tools/tool_permissions.py:111`, `:352`). The cache stores the
  response under its continuation id alone
  (`infrastructure/truncation/memory_cache.py:82`,
  `infrastructure/truncation/redis_cache.py:84`). So `tool:invoke` limits who
  may redeem an id, and nothing binds a continuation to the caller that
  produced it.

The flat path never hands a continuation id out. It returns only the call's
result (`fastmcp_server/flat_tool_projection.py:997`). Only `hangar_call`'s
result formatting carries the id (`server/tools/batch/executor.py:1782`-`:1783`),
and its docstring tells the client to redeem it with `hangar_fetch_continuation`
(`server/tools/batch/__init__.py:410`-`:412`).

## Decision

### 1. On a front door, `hangar_call` is gated exactly as a flat call is

In `front_door`, a call that `hangar_call` carries to an upstream tool passes
three gates:

- **It may name only what the caller's flat projection holds.** That is the same
  map, built by the same generation (`mcp-hangar#1367`), with each group member
  collapsed into its group. Any other target gets the answer a missing tool
  gets, and a denied target is indistinguishable from a missing one.
- **It then passes the same `BatchExecutor` gates** as a flat call.
- **It does not pass `_authorize_calls`,** so `tool:invoke` is not required.

`_authorize_calls` also refuses an anonymous caller. On a front door the
resolver's no-tenant deny (`mcp-hangar#236`) does that instead. The deny holds
because a tenant reaches the identity context from only two places: an
authenticated principal (`fastmcp_server/asgi.py:139`-`:152`) or a declared
stdio principal (ADR-026). Anything that adds a third place has to preserve this.

With those three gates, one rule decides:

- what the flat surface lists;
- what a discovery tool such as `hangar_find` may list;
- what either path will call.

That is ADR-022's rule that shown means callable, applied to the invoke path.

### 2. `egress` keeps `_authorize_calls`

In `egress`, `hangar_call` is unchanged. There it is the only invoke path, and
`tool:invoke` is the only per-principal control over which upstream tools a
principal may call. The tool-access policy there is keyed by tenant, and a caller
in `egress` may carry no tenant at all (ADR-027).

### Scope: continuation tools are not upstream tools

This decision covers calls to upstream tools. `hangar_fetch_continuation` and
`hangar_delete_continuation` are outside it. They keep `tool:invoke`, and the
front door does not project them, as today.

Removing `tool:invoke` from them would leave the continuation id as the whole
control. Binding a continuation to its caller is a separate change, and this
decision does not make it.

## Consequences

### Positive

- On a front door, listing and calling follow one rule. No path calls a target
  the surface did not list, and none refuses by permission a target it did.
- A declared stdio principal is unaffected. `tool:invoke` never decided a stdio
  call.
- Nothing a deployment runs today changes. No front door serves `hangar_call`
  yet, and `egress` is untouched. The rule takes effect with the surface
  `mcp-hangar#1370` introduces.

### Negative

- **A front door enforces no per-principal tool grant.** A custom role that
  grants `tool:invoke` on some tool names governs nothing there. The flat path
  never honoured such a grant, so no running front door loses anything.
  - An operator who moves from `egress` to `front_door` with such roles does
    lose it, and the gateway does not say so.
  - The translation is not one-to-one. The grant is by bare tool name across
    every server, while tenant policy is per server.
  - The upgrade note for `mcp-hangar#1370`'s surface has to say both.
- **`hangar_call` authorizes differently by mode:** `tool:invoke` in `egress`,
  not on a front door. The same principal making the same call can be allowed by
  one gateway and refused by another.
- **The agent role ADR-022 recommends grants nothing on a front door.** That
  role holds `tool:invoke` and nothing else. ADR-022 also kept `hangar_call` off
  the front door as "the `egress` way in". `mcp-hangar#1370` reverses that, and
  this decision assumes the reversal.
- **Truncated results become unredeemable on a front door.** Once `hangar_call`
  is served there, a truncated result will carry a continuation id for a tool the
  front door does not serve. A front-door client still cannot fetch the rest of a
  truncated result, and it will now be told how to try.

### Neutral

- On a front door, which tools a caller may use varies per tenant and never per
  principal within a tenant. That was already true of the flat path, and this
  decision extends it to `hangar_call`.

## Alternatives Considered

### 1. Require `tool:invoke` on the flat path as well

- **Rejected**: It is the stricter rule, and it keeps per-principal grants
  working. It also changes what every running HTTP front door does: a principal
  without `tool:invoke` loses every upstream tool it can call today. The control
  it preserves has never been enforced on a front door.

### 2. Keep both rules

- **Rejected**: One surface would list tools that one of its paths refuses.

### 3. Give the tool-access policy a per-principal scope

- **Deferred**: It would bring per-principal restriction back to the front door
  inside a single rule. Nobody has asked for it, and it is a change to the policy
  model rather than to the invoke gate.

## References

- Epic: `mcp-hangar#1370`. The question this follows from: `mcp-hangar#1371`.
  The projection that `hangar_call` names from: `mcp-hangar#1367`.
- Evidence: the `mcp-hangar` 2.19.1 wheel from PyPI, cited in Context. Tests:
  `tests/live/test_t2_auth.py` (`hangar_call` refuses a `viewer` over HTTP).
- The fail-closed default for a caller with no tenant: `mcp-hangar#236`. A
  denied item answered like a missing one: `mcp-hangar#905`.
- Related decisions:
  [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
  (shown means callable; `hangar_call` and the continuation tools are the invoke
  path),
  [ADR-026](ADR-026-stdio-is-an-authenticated-transport.md) (the stdio principal
  and its `viewer` default),
  [ADR-027](ADR-027-egress-is-a-trust-mode-not-a-preset.md) (row 8: the two
  paths authorize differently).
