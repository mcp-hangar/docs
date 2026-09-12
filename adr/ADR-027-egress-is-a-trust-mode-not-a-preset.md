# ADR-027: `egress` Is a Trust Mode, Not a Preset of the Front Door

**Status:** Proposed
**Date:** 2026-09-12
**Authors:** MCP Hangar Team

## Context

`mcp-hangar#1370` proposes that the front door project on demand instead of by
default. Flattening becomes opt-in per tool under a new `tool_projection.flat`
key, and the default front-door surface becomes `hangar_find` + `hangar_call` +
the management tools a caller is permitted
([ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)).

That raises a question the epic cannot answer by itself. A front door
configured with `flat: []` would serve `hangar_find`, `hangar_call` and the
permitted management tools, which is close to what `egress` serves today. If
the two are the same thing, then `flat` is not a new option. It shows that two
modes are really one mode with a parameter, and `egress` is a preset of it.
Publishing `flat` before settling this risks a third configuration shape: operators
migrate to `flat`, then migrate again when `egress` turns out to be `flat: []`
with different defaults. The project has retired an accidental parallel
structure once already. The `mcp_hangar.fastmcp_server` construction path was
removed in `mcp-hangar#963`–`#965`, and its existence alone had enabled a class
of bugs (`#592`–`#596`).

The question is answered here from the code rather than from the documented
description of the modes. The evidence is every site in the published
`mcp-hangar` 2.19.1 wheel (`mcp_hangar-2.19.1-py3-none-any.whl` from PyPI) that
reads the topology mode. Paths are relative to the `mcp_hangar/` package and
line numbers are in that wheel.

| # | Site | `egress` | `front_door` |
| --- | --- | --- | --- |
| 1 | `domain/services/tool_access_resolver.py:453` -- policy for a caller with no tenant | the server-level policy (`:482`) | `_DENY_ALL_POLICY` (`:471`) |
| 2 | `server/bootstrap/__init__.py:214` -> `fastmcp_server/flat_tool_projection.py:1073` -- the `tools/list` and `tools/call` handlers | the SDK defaults, serving the twenty-two registered `hangar_*` tools | `register_flat_tool_handlers` (`:800`): flat upstream names, per tenant |
| 3 | `server/tools/tool_permissions.py` -- the management surface | every `hangar_*` tool listed to every caller; each call passes `authorize_tool` (`:270`), which allows everything when auth is off (`:315`-`:316`) | only what `management_tools_for` (`:179`) returns: per caller, and empty when auth is off (`:228`-`:229`) or the caller is anonymous |
| 4 | `fastmcp_server/prompt_proxy.py:183`, `fastmcp_server/resource_link_read_through.py:345` -- upstream prompts and resources | not served | proxied per tenant |
| 5 | `fastmcp_server/subscription_relay.py:249` -- `subscriptions/listen` | the SDK's handler is withdrawn (`:251`) | relayed |
| 6 | `fastmcp_server/resource_link_read_through.py:148` -- resource URIs in tool results | passed through | namespaced by the owning upstream |
| 7 | `server/lifecycle.py:125` -- starting upstreams | a standalone upstream on first use; a group's members when the group loads, if its `auto_start` is on (the default, `domain/model/mcp_server_group.py:376`) | every configured upstream at boot, as well |
| 8 | `fastmcp_server/server_discover.py:88` -- `server/discover` | advertises `hangar_*` | advertises the flat projection |

Rows 2 through 8 are the surface, together with the boot-time start that fills
its catalogue before the first listing (row 7, `mcp-hangar#885` and `#1231`).
`flat: []` would bring only part of row 2 closer: in both modes an upstream tool would then be reached through
`hangar_call`, which a front door does not project today
(`server/tools/tool_permissions.py:243` excludes it and `_flat_call_tool`
answers `-32601` at `fastmcp_server/flat_tool_projection.py:938`).
`mcp-hangar#1370` governs tools only, and nothing in it touches rows 3 through
8. A front door with `flat: []` would still narrow the management surface to the
caller, proxy upstream prompts and resources, relay subscriptions, rewrite
resource URIs, and start every upstream at boot.

Row 1 is not the surface, and no projection key can reach it. The resolver is
consulted on every call path, `hangar_call` included:
`BatchExecutor._gate_tool_access` (`server/tools/batch/executor.py:1229`) passes
the caller's tenant as `member_id` at `:1245` and `:1253`. So a caller with no
tenant identity gets the server-level policy in `egress`, and nothing in
`front_door`, whichever tool it names. The repository pins this as
`test_opposite_defaults_for_same_unauthenticated_call` in
`tests/unit/test_front_door_mode.py`. Row 3 is the same fact seen from the
management side: with no principal, `egress` permits every `hangar_*` tool and
`front_door` shows none.

This splits callers into two groups, and the two modes behave differently only
for the second:

- **A caller the gateway can name**, meaning one with a tenant on the identity
  context. Both modes resolve its policy through the same resolver and differ
  only in the surface they hand it.
- **A caller it cannot name.** `egress` serves it the server-level policy and the
  full meta-API. `front_door` serves it nothing.

Two deployments put callers in the second group today. An HTTP gateway with auth
off maps every request to an anonymous principal with `tenant_id=None`
(`fastmcp_server/asgi.py:44`-`:51`). No header can supply a tenant instead. The
header extractor reads user, agent, session, principal type and correlation id,
and nothing else (`infrastructure/identity/header_extractor.py:19`-`:23`). This
is the same fact `mcp-hangar#902` found from the pinning side. A stdio process has no identity unless
`auth.stdio.principal` declares one
([ADR-026](ADR-026-stdio-is-an-authenticated-transport.md), still Proposed),
and that block is ignored when it carries no tenant (`auth/config.py:510`).
Either deployment can be configured as `front_door`. It starts, and it serves an
empty list: the process does not refuse a misconfiguration, this is what the mode
means.

ADR-026 has already chosen how a local caller reaches the front door, and it
chose by naming the caller rather than by relaxing the deny. Its boundary table
says so: `#902` "refuses to project tools to a caller nobody can name. This
names the caller. The refusal for an unnamed caller stays exactly as it is."
That treats the deny as part of the mode's definition, not as a setting of it.

## Decision

### 1. `egress` and `front_door` are two modes, and `egress` is not a preset

What separates the two modes is what the gateway does with a caller it cannot
name, not which tools it projects. `egress` serves such a caller under the
server-level policy, and `front_door` denies it. That is not a projection
parameter, and no value of `tool_projection.flat` expresses it.

The rule a reader applies:

- **The gateway must serve a caller that arrives without a tenant identity**
  (stdio with no declared principal, or HTTP with auth off): it needs `egress`.
- **Every caller carries a tenant:** it may use `front_door`, and the choice
  between the two is then a choice of surface alone (Context rows 2 through 8).

### 2. `tool_access.mode` states the caller's trust, and the surface follows from it

Until now, `tool_access.mode` has been described and read as the switch that
selects the whole surface at bootstrap. From this decision on, it states one
thing: whether a caller the gateway cannot name is served. The surfaces follow
from that answer:

- `egress` serves the `hangar_*` meta-API, the same for every caller. It cannot
  be narrowed per caller, because a caller with no principal gives the gateway
  nothing to narrow by. That is why ADR-022 left `egress` untouched.
- `front_door` serves a per-caller projection, whose shape `tool_projection`
  governs.

Which handlers are installed is still decided at bootstrap from the mode
(row 2). This decision changes what the key means, not where it is read.

### 3. `tool_projection.flat` is a front-door key

In `egress`, a `tool_projection.flat` key refuses to load. The configuration is
internally contradictory, which is the category `mcp-hangar#841` and `#902`
refused: `egress` installs no flat handlers, so the key could not be honoured,
and a file claiming to flatten tools on a gateway that serves `hangar_*` would be
the silent no-op `mcp-hangar#596` was.

This is separate from the epic's own refuse-at-load for a `front_door` with no
`flat` key. That one refuses a configuration that is valid and works, and the
epic states its own argument for it. This decision does not lend it this
precedent.

A `front_door` with `flat: []` is a valid front door. It serves identified
callers only, offers `hangar_find` + `hangar_call` + the management tools each
caller is permitted, and still projects upstream prompts and resources. It is
not `egress`, and documentation must not describe it as `egress`.

### 4. Existing `egress` deployments migrate nothing

`egress` keeps its mode, its default and its surface, and an absent
`tool_access.mode` still means `egress` (`server/config.py:865`-`:866`). No preset
is introduced, so a preset's defaults cannot come to differ from what an
existing `egress` deployment runs.

## Consequences

### Positive

- `mcp-hangar#1370` can publish `tool_projection.flat` as a front-door key
  without a later reshaping. The key controls the surface, which is a different
  axis from the one the mode selects.
- Which mode a deployment needs follows from one question about its callers.
  Nobody has to compare two tables of surfaces to decide.
- No `egress` deployment changes, and this decision needs no upgrade note.

### Negative

- Consider a deployment with auth on whose callers all carry a tenant. It sits
  in the first group, where the two modes differ only in the surface. To get a
  per-caller surface it has to change modes, so for that deployment
  `tool_access.mode` still behaves like the surface switch this decision says it
  is not. The meaning is correct, but the key alone does not make it visible.
- The rows above stay as they are, one mode check at each primitive. This is not
  the parallel structure `#963`–`#965` retired, which was two construction paths
  that drifted. It is one path with a gate per primitive, and it still means a
  new primitive has to be gated at its own site.
- The word `egress` still collides with `MCPEgressPolicy`
  ([ADR-013](ADR-013-egress-policy-enforcement-model.md)), and
  [Egress Policy Language](../cookbook/24-egress-policy-language.md) carries a
  table only to tell the two apart. This decision fixes the meaning of the mode,
  not its name. Renaming it would be a breaking change and a separate decision.

### Neutral

- Suppose ADR-026 is accepted and every transport that now serves a caller it
  cannot name gains a way to name it. `egress` would then remain only for
  deployments that turn auth off on purpose. Deprecating it would take a new ADR
  that supersedes this one and carries its own migration story.
- The size of the `hangar_call` definition, which after `mcp-hangar#1370` both
  modes would serve, is a question for that epic. It is not a difference between
  the modes.

## Alternatives Considered

### 1. One mode with an identity parameter, and `egress` as a named preset

- **Rejected**: It reopens the combination ADR-026 declined to open: a caller
  the gateway cannot name, served a projected surface (see Context). It also leaves one
  combination undefined. With no principal, `management_tools_for` returns
  nothing while `authorize_tool` permits everything (ADR-022 made the first rule
  stricter on purpose), so a preset would have to pick between two rules that
  today never meet. Finally, it is the third configuration shape `mcp-hangar#1371`
  was opened to prevent.

### 2. Remove `egress`

- **Rejected**: stdio with no declared principal and HTTP with auth off would
  each serve an empty catalogue. ADR-026 is still Proposed, and even once
  accepted it does not cover a gateway with auth turned off.

### 3. Deprecate `egress` now, on the expectation that every transport will carry identity

- **Deferred**: This depends on ADR-026 being accepted, and it still leaves HTTP
  with auth off without a mode. Revisit it as a superseding ADR if both change.

## References

- Decision issue: `mcp-hangar#1371`. Epic: `mcp-hangar#1370`. When the tool
  list is bound, which this ADR does not change: `mcp-hangar#1365`.
- Evidence: the `mcp-hangar` 2.19.1 wheel from PyPI; the sites are in the
  Context table. The repository test is `tests/unit/test_front_door_mode.py`.
- Prior construction-path consolidation: `mcp-hangar#963`, `#964`, `#965`, and
  the bugs it enabled, `#592`–`#596`.
- Refuse-at-load precedent for contradictory configuration: `mcp-hangar#841`,
  `mcp-hangar#902`.
- Related decisions:
  [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
  (the management surface follows authorization),
  [ADR-026](ADR-026-stdio-is-an-authenticated-transport.md) (stdio carries a
  declared principal),
  [ADR-013](ADR-013-egress-policy-enforcement-model.md) (the other `egress`).
- Operator guide: [Front-Door Mode](../guides/FRONT_DOOR.md).
