# ADR-028: On a Front Door, the Tool-Access Policy Is the Invoke Gate on Every Path

**Status:** Proposed
**Date:** 2026-09-13
**Authors:** MCP Hangar Team

## Context

[ADR-027](ADR-027-egress-is-a-trust-mode-not-a-preset.md) recorded that the two
paths to an upstream tool authorize a call differently. Paths and line numbers
below are in the published `mcp-hangar` 2.19.1 wheel, relative to the
`mcp_hangar/` package.

- **`hangar_call`** runs `_authorize_calls` before anything executes. With
  auth on, every call in the batch requires `tool:invoke` on the tool it names,
  and it fails closed (`server/tools/batch/__init__.py:163`-`:172`, called at
  `:518`). `tests/live/test_t2_auth.py` pins this over the real transport: a
  `viewer` is refused and a `developer` is not.
- **The flat front-door path** hands the call straight to `BatchExecutor`
  (`fastmcp_server/flat_tool_projection.py:951`-`:961`). Its gates check the
  tool-access policy for the caller's tenant, withdrawal and pins. None of them
  checks an RBAC permission.

The two paths are served in different modes today, so no surface shows both at
once. `mcp-hangar#1370` changes that: its default front-door surface is
`hangar_find` + `hangar_call` + the management tools a caller is permitted, with
`tool_projection.flat` as the opt-in. A front door would then carry both rules.

One principal would see them disagree. `viewer` is the default role of a
declared stdio principal ([ADR-026](ADR-026-stdio-is-an-authenticated-transport.md)),
and it deliberately lacks `tool:invoke`. Such a principal could call a tool
listed in `flat` and be refused the same tool through `hangar_call`. A discovery
tool that lists what the policy allows would show it tools that `hangar_call`
then refuses. That is the split between shown and callable which
[ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md) rules
out.

`tool:invoke` is also finer-grained than the built-in roles make it look. A
permission names a resource id (`domain/value_objects/security.py:141`, matched
at `:151`-`:166`), and `_authorize_calls` passes the tool name as that id. So a
custom role can grant invoke on some tools and not on others, per principal. The
tool-access policy is keyed by server, group and tenant, never by principal.

The continuation tools are the rest of the invoke path.
`hangar_fetch_continuation` and `hangar_delete_continuation` hand back the tail
of a truncated result. They are gated by `tool:invoke` through
`TOOL_PERMISSIONS`, and they also accept a grant held within a tenant
(`server/tools/tool_permissions.py:111`). Nothing else binds a continuation to
the caller that produced it:

- the cache stores a response under its continuation id alone
  (`infrastructure/truncation/memory_cache.py:82`,
  `infrastructure/truncation/redis_cache.py:84`);
- what confines it is that id, "a uuid4 batch id plus 32 random bits"
  (`server/tools/tool_permissions.py:109`).

Truncation itself runs inside `BatchExecutor.execute`
(`server/tools/batch/executor.py:983`-`:985`). So a flat call on a front door can
already return a continuation id that the front door serves no tool to redeem.
ADR-022 recorded that gap.

## Decision

### 1. On a front door, the tool-access policy gates an upstream call on every path

In `front_door`, `hangar_call` does not apply `_authorize_calls`. Each call it
carries passes the same `BatchExecutor` gates as a flat call, and nothing more:
the tool-access policy for the caller's tenant, withdrawal, and pins. A tool the
policy allows is callable by its flat name and through `hangar_call`. A tool it
denies is refused by both.

On a front door, one rule therefore decides:

- what the flat surface lists;
- what a discovery tool such as `hangar_find` (`mcp-hangar#1370`) may list;
- what either path will call.

That is ADR-022's rule that shown means callable, applied to the invoke path.

### 2. `egress` keeps `tool:invoke`

In `egress`, `hangar_call` keeps `_authorize_calls` unchanged. There it is the
only invoke path, and `tool:invoke` is the only per-principal control over which
upstream tools a principal may call. The tool-access policy there is keyed by
tenant, and a caller in `egress` may carry no tenant at all (ADR-027).

### 3. The continuation tools stay off the front door, and keep `tool:invoke`

Decision 1 does not extend to `hangar_fetch_continuation` and
`hangar_delete_continuation`. Their only other gate is the continuation id.
Removing `tool:invoke` would make the id the whole control, with no tenant or
principal check behind it.

So the front door does not project either tool, as today. Binding a
continuation to the caller that made the call is a separate change, and this
decision does not make it.

## Consequences

### Positive

- On a front door, listing and calling follow one rule. No path refuses by
  permission a tool the surface listed.
- ADR-026's default holds. A stdio `viewer` calls its own tools on a front door
  through either path, and still holds no permission over the management
  surface.
- Nothing a deployment runs today changes. No front door serves `hangar_call`
  yet, and `egress` is untouched. The rule takes effect with the surface
  `mcp-hangar#1370` introduces.

### Negative

- A front door enforces no per-principal tool restriction. A custom role that
  grants `tool:invoke` on some tools only governs nothing there. The flat path
  never honoured such a grant, so no running front door loses anything. An
  operator who moves from `egress` to `front_door` with such roles does lose it,
  though, and the gateway does not say so. The upgrade note for
  `mcp-hangar#1370`'s surface has to tell them to express that restriction as
  per-tenant tool-access policy instead.
- `hangar_call` now authorizes differently by mode: `tool:invoke` in `egress`,
  not on a front door. The same principal making the same call can be allowed by
  one gateway and refused by another.
- A front-door caller who receives a truncated result still cannot fetch the
  rest.

### Neutral

- On a front door, which tools a caller may use varies per tenant and never per
  principal within a tenant. That was already true of the flat path, and this
  decision extends it to `hangar_call`.

## Alternatives Considered

### 1. Require `tool:invoke` on the flat path as well

- **Rejected**: It is the stricter rule, and it keeps per-principal grants
  working. It also changes what every running front door does: a principal
  without `tool:invoke` loses every upstream tool, and ADR-026's default stdio
  `viewer` is exactly such a principal. Granting `viewer` `tool:invoke` would
  widen the stdio default, which ADR-026 says requires an upgrade note, and it
  would still leave every HTTP front-door principal without the permission cut
  off. The control this alternative preserves has never been enforced on a
  front door.

### 2. Keep both rules

- **Rejected**: The surface would list tools that one of its paths then refuses.

### 3. Give the tool-access policy a per-principal scope

- **Deferred**: It would bring per-principal restriction back to the front door
  inside a single rule. Nobody has asked for it, and it is a change to the
  policy model rather than to the invoke gate.

## References

- Epic: `mcp-hangar#1370`. The question this follows from: `mcp-hangar#1371`.
- Evidence: the `mcp-hangar` 2.19.1 wheel from PyPI, cited in Context. Tests:
  `tests/live/test_t2_auth.py` (`hangar_call` refuses a `viewer`).
- Related decisions:
  [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
  (shown means callable; `hangar_call` and the continuation tools are the invoke
  path),
  [ADR-026](ADR-026-stdio-is-an-authenticated-transport.md) (the `viewer`
  default and why it lacks `tool:invoke`),
  [ADR-027](ADR-027-egress-is-a-trust-mode-not-a-preset.md) (row 8: the two
  paths authorize differently).
