# ADR-027: `egress` Is a Trust Mode, Not a Preset of the Front Door

**Status:** Accepted
**Date:** 2026-09-12
**Authors:** MCP Hangar Team

## Context

mcp-hangar#1370 proposes discovery on demand and opt-in flattening on the front
door. That raises a mode question: if a future front door exposes
`hangar_find` and `hangar_call`, is `egress` only a preset of the same mode?

The original analysis used core 2.19.1. At that time flat calls omitted the
role-based invoke check. That was repaired in mcp-hangar#1623, released in
2.24.0. A missing authorization check is not a reason to preserve two modes.
ADR-028 records the shared authorization and transport-identity contract.

The remaining distinction is deliberate. For upstream tools, `front_door`
requires a tenant and resolves a per-tenant projection. `egress` permits the
policy without a tenant layer when the caller has no tenant. The modes also
select different protocol surfaces: management/meta-tools in egress, projected
tools plus the front-door prompt/resource/subscription paths in front_door.
A surface option alone does not express all those choices.

The shared-scope work in mcp-hangar#1763 and discovery work in mcp-hangar/mcp-hangar#1373 remain
implementation tasks. This record does not claim that their proposed keys,
tools or surface defaults are already served.

## Decision

### 1. Keep two modes

`egress` remains a separate supported mode, not a named preset of
`front_door`. The choice bounds the supported combinations rather than
exposing a parameter for every identity and protocol-surface difference.

### 2. Define the mode by its no-tenant policy

For upstream invocation, `front_door` denies a caller without a tenant.
`egress` evaluates the policy without a tenant layer. A role grant does not
create a tenant or override this policy decision.

When auth is enabled, both invoke entry paths require `tool:invoke`, as
ADR-028 specifies. Auth-disabled behavior is also governed by ADR-028.
Invocation RBAC is not a difference between these modes.

Management visibility remains a principal/permission decision under ADR-022.
Permission to manage a gateway does not imply that the principal has the
tenant needed for front-door upstream invocation.

### 3. A future flat-projection option belongs to the front door

If mcp-hangar#1370 introduces `tool_projection.flat`, it is a front-door
surface choice. Under egress it must be refused rather than accepted as a
silent no-op. A front door exposing no flat tool names does not thereby become
egress: its no-tenant rule and other protocol surfaces still differ.

This is a design constraint on future implementation, not a statement that
the key or `hangar_find` already exists. The decision to require existing
front-door installations to choose a surface explicitly, its migration and
the default surface remain the responsibility of mcp-hangar/mcp-hangar#1370/#1373.

### 4. Existing egress deployments keep their mode

No preset, rename or default change is introduced by this record.
Existing egress installations have no migration to perform because of this
decision. Future front-door migration must be documented by its own change.

## Consequences

### Positive

- The mode has a stable identity/policy meaning after both entry paths share
  the same invocation authorization.
- Existing egress deployments retain their behavior.
- A new surface does not silently relax the no-tenant front-door boundary.

### Negative

- Bootstrap still selects different handlers and protocol features by mode.
  Each additional primitive needs parity and reachability coverage.
- When all callers have tenants, the visible difference may mostly be the
  exposed surface; the mode name still carries more than that surface choice.
- The name egress also appears in MCPEgressPolicy, so documentation must
  distinguish a serving mode from the L7/network policy object.

### Neutral

- A later decision may unify the modes, but it must define and test the
  additional combinations and supersede this record explicitly.

## Alternatives Considered

### 1. One mode with independently configurable features

Rejected here. It exposes combinations the project does not currently need
and would require either tests or explicit load-time refusal for each one.

### 2. Remove egress

Rejected here. A deployment intentionally serving callers without tenants
would lose its existing serving mode.

### 3. Preserve an RBAC difference as the reason for two modes

Rejected. The flat-path omission was a security defect, repaired in 2.24.0.
Authorization follows ADR-028 on both paths.

## References

- [ADR-028](ADR-028-the-front-door-invoke-gate-is-the-tool-access-policy.md).
- [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md).
- [ADR-013](ADR-013-egress-policy-enforcement-model.md).
- [mcp-hangar#1371](https://github.com/mcp-hangar/mcp-hangar/issues/1371):
  the mode decision.
- [mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623):
  authorization repair, released in 2.24.0.
- `tests/unit/test_front_door_mode.py`.
- [Front-Door Mode](../guides/FRONT_DOOR.md).
