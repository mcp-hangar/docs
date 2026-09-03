# ADR-026: Stdio Is an Authenticated Transport, and the Config Names Its Principal

**Status:** Proposed
**Date:** 2026-09-03
**Authors:** MCP Hangar Team

## Context

Hangar's governance model resolves every decision from an identity. Tool-access
policy is evaluated per tenant, digest pins may be scoped per tenant, and the
management surface is whatever the caller is allowed to call (ADR-022). Since
`#902` the front door is fail-closed on that identity: a caller Hangar cannot
name gets nothing rather than everything.

Identity arrives through one door. `IdentityMiddleware`
(`infrastructure/identity/middleware.py`) is ASGI middleware; its first act is

```python
if scope["type"] not in ("http", "websocket"):
    await self.app(scope, receive, send)
    return
```

and the HTTP auth middleware composes on top of the same request normalization.
Everything downstream reads `identity_context_var`.

Stdio has no ASGI scope. `run_stdio` (`server/lifecycle.py:321`) calls
`mcp_server.run()` on a process whose transport is a pipe: no request, no
headers, no middleware, and therefore no identity context. The consequence is
not a degraded mode, it is an unreachable one. With
`tool_access.mode: front_door` and a client speaking over stdio, the
per-request flat map is built for `tenant_id = None`,
`_compute_effective_policy` takes its deny-all branch, and `tools/list`
returns zero tools with `empty_projection reason=no_identity ... Fail-closed
deny` in the log. The mode Hangar recommends is the mode a local client cannot
use.

That leaves the default `egress` mode as the only working local configuration,
where a caller sees twenty-two `hangar_*` tools -- roughly eleven thousand
tokens of `tools/list` for a single upstream -- and reaches its own tools only
indirectly through `hangar_call`. The governance features work there; the
projection is simply the wrong shape for a laptop, and the wrong shape is the
one every new user meets first.

The underlying question is what authentication means on a transport that has no
channel to carry a credential. A stdio server is not listening on anything. It
was **spawned** -- by Claude Code, Cursor, Claude Desktop, or a shell -- as a
child process of a session that the operating system already authenticated. A
credential presented over that pipe would be a credential the same OS user could
read out of the config file, so checking it would prove nothing that the spawn
did not already prove.

## Decision

**The process that spawns Hangar over stdio is the trust boundary. The
configuration file names the principal that boundary implies; Hangar checks no
credential over stdio, because none exists to check.**

### The config block

```yaml
auth:
  stdio:
    principal:
      id: local-user          # required
      tenant_id: local        # required
      roles: [viewer]         # optional; default [viewer]
```

When the serving transport is stdio and the block is present, the session's
identity context is set from the block for every request on that session. When
the block is absent, behavior is byte-identical to 2.17.1: the caller is
anonymous and the front door stays empty. This is what makes the change a minor
rather than a breaking one -- no existing configuration acquires an identity it
did not declare.

### Boundaries of the decision

| Question | Answer |
| --------- | ------- |
| Does HTTP read this block? | No. HTTP has a credential channel and keeps using it. The block is ignored there, and `--unsafe-no-auth` semantics are unchanged. |
| Is a credential ever checked over stdio? | No. The spawn is the authentication event. A shared secret in the same file the principal is declared in would authenticate the file, not the caller. |
| Does this weaken `#902`? | No. `#902` refuses to project tools to a caller nobody can name. This names the caller. The refusal for an unnamed caller stays exactly as it is. |
| What may the principal manage? | Whatever its `roles` allow through `TOOL_PERMISSIONS` (`#909`/`#910`/`#912`). No tool becomes reachable because the transport is stdio. |

### Why `viewer` is the default role

`roles: []` would project no management surface at all, which is the safest
default and also an unhelpful one: a user whose first run misbehaves has no way
to ask the gateway what it thinks is happening. `viewer` (`auth/roles.py:216`)
already exists, is read-only by construction, and holds no permission that can
change fleet state -- `providers:read`, `provider:read`, `provider:list`,
`tool:list`, `metrics:read`, `group:read`, `group:list`, `discovery:read`.

`viewer` deliberately does not hold `tool:invoke`. That permission gates
`hangar_call`, whose `_authorize_calls` checks it per call; the flat front-door
path authorizes an upstream call through the tool-access policy inside
`BatchExecutor` instead. A local principal can therefore call its own tools
while holding no permission to invoke anything through the management surface.

Widening this default later requires an upgrade note, because a role is a
grant: adding one silently would hand an existing local deployment a management
surface its configuration never asked for.

### What must move with it

- `refuse_pins_that_no_caller_can_match` (`#902`) must treat a per-tenant pin
  written for the stdio principal's `tenant_id` as matchable. Otherwise the
  first pinned local config refuses to start.
- `empty_projection{reason=no_identity}` must not fire over stdio when the
  block is present. The metric is how the fail-closed path is observed; leaving
  it firing on a configuration that works would make it useless.
- `auth` is a closed key set in `server/config_schema.py`. `stdio` has to be
  added there in the same change, or a config carrying it is rejected as a
  typo -- which is the schema working as designed.

## Consequences

### Positive

- The recommended projection becomes reachable locally. `front_door` over stdio
  serves the upstream's own tool names, so a client sees the tools it came for
  and not the gateway's control plane.
- Per-tenant governance -- policy rules, digest pins -- applies to a local run
  without inventing a second, transport-specific policy path. The stdio
  principal is an ordinary tenant.
- The fail-closed default survives. Absent configuration still yields an
  anonymous caller and an empty front door, so the change cannot silently open
  an existing deployment.
- The trust story is stated rather than implied. A reader can disagree with
  "the spawn is the authentication event" on the record, instead of discovering
  an undocumented anonymous path.

### Negative

- Anyone who can write the config file can name any principal, including one
  with `roles: [admin]`. On a laptop that is the same person; on a shared host
  with a world-writable config it is not, and the file's permissions become a
  security control that nothing in Hangar enforces.
- A second way to acquire an identity now exists. Two paths to one context
  variable is the shape that produces "works over HTTP, not over stdio" bugs,
  so the stdio path has to be exercised by its own e2e test rather than
  inferred from the HTTP one.
- Declared identity cannot be revoked. There is no session to invalidate and no
  token to expire; stopping the process is the only revocation.

### Neutral

- The block is inert for every containerized and clustered deployment, which
  serve over HTTP. This is a decision about the local funnel, and it adds a key
  those deployments will never set.
- The default role is a judgment call about first-run legibility, not a
  security boundary. A deployment that wants zero management surface locally
  sets `roles: []` and loses nothing else.

## References

- ADR-022: The Management Surface Is Whatever the Caller Is Allowed to Call --
  the table this decision routes `roles` through.
- `mcp-hangar#902`: fail-closed projection for a caller with no identity.
- `mcp-hangar#1190`: implementation of this ADR (WS-0 of the 2.18.0 funnel epic,
  `mcp-hangar#1189`).
- `infrastructure/identity/middleware.py`, `server/lifecycle.py:321`,
  `fastmcp_server/flat_tool_projection.py`, `auth/roles.py:216`.
