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

A front door configured with `flat: []` would then serve `hangar_find`,
`hangar_call` and the permitted management tools, which is close to what
`egress` serves today. `mcp-hangar#1371` asks whether the two are the same
thing. If they are, `flat` is not a new option: it shows that two modes are one
mode with a parameter, and `egress` is a preset of it. Settling this before
`flat` is published avoids a third configuration shape, in which operators
migrate to `flat` and then migrate again. The project has retired an accidental
parallel structure before. The `MCPServerFactory` construction path was retired
in `mcp-hangar#963`–`#965`, and its existence alone had enabled a class of bugs
(`#592`, `#594`–`#596`).

The answer is taken from the published `mcp-hangar` 2.19.1 wheel
(`mcp_hangar-2.19.1-py3-none-any.whl` from PyPI), not from the documented
description of the modes. Paths are relative to the `mcp_hangar/` package and
line numbers are in that wheel.

### Where the code reads the mode

| # | Site | `egress` | `front_door` |
| --- | --- | --- | --- |
| 1 | `domain/services/tool_access_resolver.py:453` -- policy for a caller with no tenant | the policy with no tenant layer: server-level over the `_global` floor for a standalone server (`:442`-`:447`, `:482`), the group and member merge for a group | `_DENY_ALL_POLICY` (`:471`) |
| 2 | `server/bootstrap/__init__.py:214` -> `fastmcp_server/flat_tool_projection.py:1073` -- the `tools/list` and `tools/call` handlers | the SDK defaults, serving the twenty-two registered `hangar_*` tools | `register_flat_tool_handlers` (`:800`): flat upstream names, per tenant |
| 3 | `fastmcp_server/prompt_proxy.py:183`, `fastmcp_server/resource_link_read_through.py:345` -- upstream prompts and resources | not served | proxied per tenant |
| 4 | `fastmcp_server/subscription_relay.py:249` -- `subscriptions/listen`, from which the advertised subscription flags are derived | the SDK's handler is withdrawn (`:251`) | relayed |
| 5 | `fastmcp_server/resource_link_read_through.py:148` -- resource URIs in tool results | passed through | namespaced by the owning upstream |
| 6 | `server/lifecycle.py:125` -- starting upstreams | a standalone upstream on first use; a group's members when the group loads, since `auto_start` defaults to on (`server/config.py:737`) | every configured upstream at boot, as well |
| 7 | `fastmcp_server/server_discover.py:88` -- `server/discover` | advertises `hangar_*` | advertises the flat projection |

### What follows from the handlers row 2 installs

These rows do not read the mode. They follow from which call path each set of
handlers sends a request down.

| # | Concern | `egress` | `front_door` |
| --- | --- | --- | --- |
| 8 | Invoking an upstream tool | through `hangar_call`, whose `_authorize_calls` requires `tool:invoke` per call when auth is on (`server/tools/batch/__init__.py:518`) | through `_flat_call_tool`, which hands the call straight to `BatchExecutor` (`fastmcp_server/flat_tool_projection.py:951`-`:961`). `BatchExecutor` has no RBAC gate, only the tool-access policy. |
| 9 | The management surface | every `hangar_*` tool listed to every caller. Each call passes `authorize_tool` (`server/tools/tool_permissions.py:270`), which allows everything when auth is off (`:315`-`:316`) and refuses an anonymous principal when it is on. | only what `management_tools_for` (`:179`) returns for the caller's principal: empty when auth is off (`:228`-`:229`) or the principal is anonymous |

ADR-026 recorded the difference in row 8 from the other side: its default role,
`viewer`, lacks `tool:invoke`, which gates `hangar_call` and not the flat path.

### What the rows add up to

The two modes differ in three ways, and they are decided by different
properties of the caller.

**1. A caller with no tenant, for upstream tools (row 1).** The resolver is
consulted on every upstream call path, `hangar_call` included:
`BatchExecutor._gate_tool_access` (`server/tools/batch/executor.py:1229`) passes
the caller's tenant at `:1245` and `:1253`. With a tenant, both modes resolve the
same tool-access policy. Without one, `egress` applies the policy with no tenant
layer and `front_door` denies every upstream tool, the fail-closed default from
`mcp-hangar#236`. The repository tests this at the executor level:
`test_front_door_no_identity_blocks_call` and
`test_egress_no_identity_uses_server_policy` in
`tests/unit/test_front_door_mode.py`.

A caller reaches the resolver with no tenant in three ways:

- over HTTP with auth off, where there is no principal, so no identity
  (`fastmcp_server/asgi.py:139`-`:151`);
- over stdio, unless `auth.stdio.principal` declares one
  ([ADR-026](ADR-026-stdio-is-an-authenticated-transport.md), Proposed), and a
  declaration without a tenant is ignored (`auth/config.py:510`);
- as an authenticated principal that carries no tenant, since
  `Principal.tenant_id` is optional (`domain/value_objects/security.py:77`).

No header can supply a tenant: the header extractor reads user, agent, session,
principal type and correlation id, and nothing else
(`infrastructure/identity/header_extractor.py:19`-`:23`). A front door starts
in all three cases. It serves no upstream tool to such a caller, and the process
does not refuse the configuration.

**2. Who may invoke at all (row 8).** This is decided by the call path, not by
the tenant. `egress` requires `tool:invoke` of every principal that invokes an
upstream tool. `front_door` does not; the tool-access policy is the whole gate.
With auth off, neither mode checks.

**3. The surface (rows 2 through 7, and 9).** This includes what the
management surface shows. That is decided by the principal and by whether auth
is on, not by the tenant. So an authenticated principal with no tenant is shown,
and may call, its permitted management tools on a front door, while it is denied
every upstream tool there.

`flat: []` would change only part of this. A front door would then serve
`hangar_call`. That means dropping it from the exclusion at
`server/tools/tool_permissions.py:243` and dispatching it where `_flat_call_tool`
now answers `-32601` (`fastmcp_server/flat_tool_projection.py:938`). Rows 7 and 9
would gain `hangar_find` and `hangar_call`. Rows 1 and 3 through 6 are untouched
by `mcp-hangar#1370`. So is the difference in row 8 between the two paths, and on
a front door it would now sit side by side on one surface.

## Decision

### 1. `egress` stays a mode of its own, and is not made a preset

This is a choice. The evidence above establishes that a `front_door` with
`flat: []` is not `egress`: it still denies upstream tools to a caller with no
tenant, still skips `tool:invoke` on the flat path, and still projects prompts,
resources and subscriptions. The evidence does not show that the two could never
be written as one mode with parameters. `mcp-hangar#1371` lists a named preset as
an acceptable answer.

Two modes are kept because a preset would need one parameter for each
difference above: the treatment of a caller with no tenant, the management
listing, and each of rows 3 through 6. Every combination except the two presets
would then need a test or a load-time refusal. The one combination anyone has
asked for is a projected surface for a caller with no tenant. ADR-026 proposes to
reach it by giving the caller a tenant, not by relaxing the `#236` deny. Two modes
keep two combinations, and both are tested.

### 2. The mode is defined by how it treats a caller with no tenant

`tool_access.mode` is defined by row 1. `egress` serves a caller with no tenant
the policy without a tenant layer, and `front_door` denies it upstream tools.
Row 1 is chosen as the definition because no surface key can reach it and
`mcp-hangar#1370` does not move it.

The other differences follow from the mode by choice, not by necessity.
ADR-022 records this for the management surface: narrowing `egress` per caller
"is available and deliberately not taken here", to keep the default surface
stable. The key still switches the handlers and rows 3 through 7 at bootstrap.
This decision says what the mode means. It does not reduce what the key switches.

### 3. `tool_projection.flat` is a front-door key

In `egress`, a `tool_projection.flat` key refuses to load. Of the
`tool_projection` keys, `flat` is the only one with no effect under `egress`.
`pins`, `withdrawn` and `tenant_overrides` are enforced in `BatchExecutor` in
both modes. A key that cannot be honoured is internally contradictory
configuration, the category `mcp-hangar#841` and `#902` refused. A file that
claims to flatten tools on a gateway serving `hangar_*` would be the silent
no-op `mcp-hangar#596` was.

This is separate from the epic's own refuse-at-load for a `front_door` with no
`flat` key. That one refuses a configuration that is valid and works, and the
epic states its own argument for it. This decision does not lend it this
precedent.

A `front_door` with `flat: []` is a valid front door. It serves upstream tools
only to callers with a tenant, offers `hangar_find` + `hangar_call` + the
management tools each principal is permitted, and still projects upstream
prompts and resources. It is not `egress`, and documentation must not describe
it as `egress`.

### 4. Existing `egress` deployments migrate nothing

`egress` keeps its mode, its default and its surface, and an absent
`tool_access.mode` still means `egress` (`server/config.py:865`-`:866`). No preset
is introduced, so a preset's defaults cannot come to differ from what an
existing `egress` deployment runs.

## Consequences

### Positive

- `mcp-hangar#1370` can publish `tool_projection.flat` as a front-door key
  without a later reshaping on this argument. The property that defines the mode
  is one `flat` cannot express.
- Which mode a deployment needs follows from one question: must it serve
  upstream tools to a caller with no tenant?
- No `egress` deployment changes, and this decision needs no upgrade note.

### Negative

- Once `mcp-hangar#1370` serves `hangar_call` on a front door, two invocation
  rules meet on one surface. A tool listed in `flat` needs no `tool:invoke`, and
  the same tool reached through `hangar_call` does. A principal holding `viewer`
  could call the first and not the second. This decision changes neither rule,
  and the epic that puts both paths on one surface inherits the disagreement.
- Consider a deployment whose callers all carry a tenant. For it, the modes
  differ only in invocation RBAC and surface, and changing modes is how it gets
  a per-caller surface. There the key behaves as the surface switch the
  definition in Decision 2 says it is not.
- The mode is still read at one gate per primitive (rows 1 through 7), so a new
  primitive has to be gated at its own site. That is not the structure
  `#963`–`#965` retired, which was a second construction path, but it is a list
  someone has to keep complete.
- The word `egress` still collides with `MCPEgressPolicy`
  ([ADR-013](ADR-013-egress-policy-enforcement-model.md)), and
  [Egress Policy Language](../cookbook/24-egress-policy-language.md) carries a
  table only to tell the two apart. This decision defines the mode, not its
  name. Renaming it would be a breaking change and a separate decision.

### Neutral

- If every caller with no tenant later gains a tenant, `egress` would remain
  only for deployments that turn auth off on purpose. Deprecating it would need
  an ADR that supersedes this one.

## Alternatives Considered

### 1. One mode with parameters, and `egress` as a named preset

- **Rejected**: At its strongest, this removes a mode and makes every surface
  key apply everywhere. It is rejected for the cost stated in Decision 1: a
  parameter per difference, and a test or a refusal for every combination
  outside the two presets. It is not rejected on the grounds that
  `mcp-hangar#1371` ruled it out, because #1371 did not.

### 2. Remove `egress`

- **Rejected**: Every deployment whose callers carry no tenant would serve them
  no upstream tool. That covers HTTP with auth off and stdio with no declared
  principal. ADR-026 is Proposed, and it does not cover HTTP with auth off.

### 3. Deprecate `egress` now, on the expectation that every caller will carry a tenant

- **Deferred**: It depends on ADR-026 being accepted, and it still leaves HTTP
  with auth off with no mode. Revisit it as a superseding ADR if both change.

## References

- Decision issue: `mcp-hangar#1371`. Epic: `mcp-hangar#1370`. When the tool
  list is bound, which this ADR does not change: `mcp-hangar#1365`.
- Evidence: the `mcp-hangar` 2.19.1 wheel from PyPI, cited in the tables above.
  Repository tests: `tests/unit/test_front_door_mode.py`.
- The front-door deny: `mcp-hangar#236`. Pins and a caller with no tenant:
  `mcp-hangar#902`, `#907`.
- The retired construction path: `mcp-hangar#963`, `#964`, `#965`, and the bugs
  it enabled, `#592`, `#594`–`#596`.
- The refuse-at-load precedent for contradictory configuration: `mcp-hangar#841`,
  `#902`.
- Related decisions:
  [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md)
  (the management surface follows authorization),
  [ADR-026](ADR-026-stdio-is-an-authenticated-transport.md) (stdio carries a
  declared principal),
  [ADR-013](ADR-013-egress-policy-enforcement-model.md) (the other `egress`).
- Operator guide: [Front-Door Mode](../guides/FRONT_DOOR.md).
