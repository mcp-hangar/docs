# ADR-028: One Invoke Authorization Contract for HTTP and Stdio

**Status:** Accepted
**Date:** 2026-09-13
**Authors:** MCP Hangar Team

## Context

The first proposal gave the front door's tool-access policy sole responsibility
for invocation and omitted `tool:invoke`. It matched an omission in the flat
call path, not an intended exception to role-based authorization. Core
[mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623), released in
2.24.0, repaired that omission and applied the same invocation authorization to
flat calls and `hangar_call`, including a declared stdio principal.

[ADR-026](ADR-026-stdio-is-an-authenticated-transport.md) correctly chose the
spawning process as the stdio authentication boundary. Its explanation that
`tool:invoke` decides nothing on stdio is no longer true when auth is enabled.
This decision supersedes ADR-026, carries its identity boundary and defaults
forward, and records the authorization rule the repaired implementation serves.
It does not grant additional roles or change an existing configuration.

HTTP has a credential-bearing request. Stdio has no request or credential
channel: the OS-authenticated session spawns a child, and the configuration
declares the principal that boundary implies. Authentication and authorization
remain separate questions on both transports.

## Decision

### 1. Resolve identity from the serving transport

HTTP uses the authenticated principal on that request. A request with no
principal never borrows the declared stdio principal.

Stdio uses `auth.stdio.principal`, when configured, with no credential checked
over the pipe. The declaration requires an id and tenant_id; its roles default
to `[viewer]`. Anyone who can modify that configuration can change its
declared identity, so file ownership and permissions remain part of the trust
boundary. The declaration cannot be revoked by token expiry; changing it
requires restarting the process.

Without the declaration, stdio acquires no identity from this mechanism.
A front-door caller without a tenant is denied upstream tools, as ADR-027
requires. HTTP does not consume the stdio declaration.

### 2. Apply one invocation authorization rule

When authentication/authorization is enabled, every upstream invocation on
the flat front-door path and through `hangar_call` requires `tool:invoke`.
A missing or anonymous principal is refused; the declared stdio principal is
authorized against its declared built-in roles.

The shared authorization check is `_authorize_calls`; the flat path reaches
it through `_authorize_flat_call`. The authorization layer remains outside
the executor's governance chain, and neither serving path may omit it.

When auth is explicitly disabled, the existing authorization bypass remains.
That does not bypass tool-access policy, withdrawal, digest pins, approval,
L7 policy or other configured governance controls. In particular, disabling
auth does not create the tenant a front-door caller needs.

The `viewer` role remains read-only and lacks `tool:invoke`. Under enabled
auth it cannot invoke an upstream merely because stdio declares it or a
catalogue exposes the tool. A deployment needing invocation grants an
appropriate role explicitly. This ADR does not widen the default role.

### 3. Tool-access policy narrows an authorized call

A role grant does not override server, group, member or tenant policy.
Withdrawal, digest enforcement, approvals and the remaining runtime controls
still apply. A tool-access allow is likewise not a substitute for a role grant
when auth is enabled.

Tools hidden by policy remain indistinguishable from missing names for ordinary
callers. The refusal path must preserve the non-disclosure contract in
mcp-hangar#905; documenting authorization must not introduce enumeration.

### 4. Management authorization remains distinct

A management operation uses its `TOOL_PERMISSIONS` entry. The front door's
management listing follows those permissions, as ADR-022 specifies. A stdio
principal receives no management permission solely from the transport.

This ADR does not choose the permission for `hangar_find`, implement the new
front-door surface, or introduce `tool_projection.flat`. Those changes remain
in mcp-hangar#1370/#1373. It does not change continuation ownership or expose
continuation tools on a surface that currently excludes them.

## Consequences

### Positive

- Invocation authorization has the same meaning over HTTP and stdio and on
  the flat and batch entry paths.
- The process-spawn trust boundary remains explicit without adding a
  credential that the same local user could read from configuration.
- Roles and tenant policy retain separate, testable responsibilities.
- The documented contract agrees with the security repair shipped in 2.24.0.

### Negative

- An enabled-auth local deployment declaring only `viewer` cannot invoke
  upstream tools. Examples promising invocation must grant it explicitly.
- The config file can declare a privileged stdio identity; its filesystem
  permissions cannot be replaced by checking a secret in that same file.
- Auth-disabled deployments retain a different authorization posture, which
  must be described explicitly rather than inferred from transport names.

### Neutral

- The default role stays `viewer`; this record adds no implicit grant.
- The same policy can still produce different runtime outcomes because of
  health, budgets or approval state. Authorization parity does not promise
  execution success.

## Alternatives Considered

### 1. Tool-access policy alone on the front door

Rejected. This was the earlier ADR-028 proposal. A viewer could invoke through
the flat path while the same role was refused through `hangar_call`, the
security defect repaired by mcp-hangar#1623.

### 2. Exempt stdio from authorization when auth is enabled

Rejected. Process spawning establishes identity; it does not grant every
operation to that identity. The declared principal already has roles.

### 3. Add a shared credential to the stdio config

Rejected. It would authenticate a file to the user who can already read and
modify that file, without strengthening the spawn boundary.

## References

- [ADR-026](ADR-026-stdio-is-an-authenticated-transport.md), superseded here.
- [ADR-022](ADR-022-the-management-surface-is-what-the-caller-may-call.md).
- [ADR-027](ADR-027-egress-is-a-trust-mode-not-a-preset.md).
- [mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623):
  invocation parity and declared stdio roles, released in 2.24.0.
- [mcp-hangar#1631](https://github.com/mcp-hangar/mcp-hangar/pull/1631):
  management authorization for the declared stdio principal.
- `tests/unit/test_the_flat_call_checks_tool_invoke.py`.
- `tests/live/test_t0_stdio_tool_invoke.py` and
  `tests/live/test_t2_front_door_tool_invoke.py`.
