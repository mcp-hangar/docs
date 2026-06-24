# Front-Door Mode & Per-Tenant Tool Governance

Hangar 1.3 introduces a **topology mode** that controls how Hangar treats the
callers in front of it. The default mode, `egress`, assumes Hangar sits behind
trusted internal callers and proxies them out to back-end MCP servers. The new
`front_door` mode is the inverse: Hangar faces untrusted, external agents and
applies fail-closed, per-tenant tool governance on every call.

This guide covers what front-door mode is, how it differs from egress, how
per-tenant tool policy and tool withdrawal work, and how Hangar advertises
itself as an OAuth 2.0 protected resource (RFC 9728).

## Egress vs. Front-Door

The topology mode is set once at the top level of your config under
`tool_access.mode`:

```yaml
tool_access:
  mode: front_door   # "egress" (default) | "front_door"
```

| | `egress` (default) | `front_door` |
|---|---|---|
| Caller trust | Trusted internal callers | Untrusted external agents |
| Caller without a tenant identity | Allowed (server-level policy applies) | **Denied** (fail-closed) |
| Tool surface exposed to clients | Full `hangar_*` meta-API | Flat per-tenant backend tool names |
| Use case | Internal control plane / proxy | Public or multi-tenant front door |

If `tool_access.mode` is absent or set to an unrecognized value, Hangar
defaults to `egress` and logs a warning — a typo never silently activates the
stricter mode, and existing deployments are never broken by the upgrade.

> Source: `src/mcp_hangar/server/config.py` (`_init_topology_mode_from_config`),
> `src/mcp_hangar/domain/services/tool_access_resolver.py` (`TopologyMode`).

## Fail-Closed Default

The defining behavior of front-door mode is that a caller with **no tenant
identity is denied every tool**, regardless of target. This check fires before
any server-, group-, or member-level policy is evaluated, so an unauthenticated
external caller can never reach a tool — not even through a group path.

Concretely, when the resolver is in `front_door` mode and the caller has no
member/tenant (`member_id is None`), it returns a deny-all policy
(`deny_list=("*",)`). In `egress` mode the same caller would fall through to the
server-level policy.

> Source: `src/mcp_hangar/domain/services/tool_access_resolver.py`
> (deny-all sentinel `_DENY_ALL_POLICY`, the front-door guard in the policy
> resolution path).

## Per-Tenant Identity

The tenant of a request is carried on the caller identity. The
`CallerIdentity` value object has a `tenant_id` field, which is populated from a
JWT claim when OIDC authentication is enabled.

```python
@dataclass(frozen=True)
class CallerIdentity:
    user_id: str | None
    agent_id: str | None
    session_id: str | None
    principal_type: PrincipalType = "anonymous"
    tenant_id: str | None = None
```

The JWT claim that maps to `tenant_id` is configurable and defaults to
`tenant_id`:

```yaml
auth:
  oidc:
    enabled: true
    issuer: https://auth.company.com
    audience: mcp-hangar
    tenant_claim: tenant_id   # default; the JWT claim read into CallerIdentity.tenant_id
```

When an authenticated request comes in over HTTP, Hangar bridges the principal
into the request-scoped identity context so the per-tenant enforcement and the
flat tool projection can read `caller.tenant_id`.

> Source: `src/mcp_hangar/domain/value_objects/identity.py` (`CallerIdentity`),
> `src/mcp_hangar/auth/config.py` (`tenant_claim` default),
> `src/mcp_hangar/fastmcp_server/asgi.py` (identity bridge on the request path).

## Per-Tenant Tool Access Policy

On top of the existing server-level allow/deny lists, 1.3 adds **member-scope**
(per-tenant) tool access policies. These are declared per MCP server under
`tool_access.member`, keyed by tenant ID:

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: http://payments:8080/mcp
    tool_access:
      member:
        "tenant:a":
          deny_list: [refund]          # tenant:a cannot call "refund"
        "tenant:b":
          allow_list: [charge, refund] # tenant:b is restricted to these two
```

The resolver merges policies as **server → member**: the server-level policy is
combined with the matching per-tenant policy on the live call path. The
effective decision is enforced when a tool is invoked, not only at list time.

> Source: `src/mcp_hangar/server/config.py` (parsing of `tool_access.member`,
> `set_standalone_member_policy`),
> `src/mcp_hangar/domain/services/tool_access_resolver.py`
> (`is_tool_allowed`, server→member merge),
> `src/mcp_hangar/server/tools/batch/executor.py` (live call-path check,
> `ToolAccessDeniedError` on deny).

## Tool Withdrawal

Hangar 1.3 can withdraw individual tools — make them disappear from the
projection that callers see and refuse to route them — either at runtime or via
config. Withdrawals are tracked by the **`ToolProjectionRegistry`** read-model,
which is the single source of truth for whether a tool is active for a given
tenant.

The effective withdrawal of a tool is `config OR runtime`: a config-declared
withdrawal and a runtime withdrawal are independent overlays, and a tool is
withdrawn if either says so.

### Runtime withdrawal (REST API)

Two admin endpoints withdraw and restore a tool at runtime. Both require the
admin permission (the `lifecycle` action on the `mcp_servers` resource) and
publish a domain event (`ToolWithdrawn` / `ToolRestored`).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/tools/{server}/{tool}/withdraw` | Withdraw a tool at runtime |
| `POST` | `/api/admin/tools/{server}/{tool}/restore` | Remove a runtime withdrawal |

Both accept an optional JSON body with a `tenant_id`. Omitting it (or sending
`null`) withdraws/restores **globally for all tenants**; providing one scopes
the action to that tenant.

```bash
# Withdraw "refund" from the "payments" server for one tenant
curl -X POST http://localhost:8000/api/admin/tools/payments/refund/withdraw \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "tenant:a"}'
```

```json
{"withdrawn": true, "mcp_server": "payments", "tool": "refund", "tenant_id": "tenant:a"}
```

`restore` affects only the runtime overlay. A config-declared withdrawal
persists independently.

> Source: `src/mcp_hangar/server/api/admin_tools.py`,
> mounted at `/admin/tools` under the `/api` router in
> `src/mcp_hangar/server/api/router.py`.

### Config-declared withdrawal

Withdrawals can also be declared in config under each MCP server's
`tool_projection` block. These are applied as a config overlay on the
`ToolProjectionRegistry`, so the named tools resolve as withdrawn even before
they are discovered from the back end, and they survive reloads.

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: http://payments:8080/mcp
    tool_projection:
      withdrawn: [legacy_charge]          # withdrawn for ALL tenants
      tenant_overrides:
        "tenant:a":
          withdrawn: [refund]             # withdrawn for tenant:a only
```

> Source: `src/mcp_hangar/server/config.py` (parsing of `tool_projection`,
> `set_config_withdrawal`),
> `src/mcp_hangar/application/read_models/tool_projection.py`
> (`ToolProjectionRegistry`).

## Flat Per-Tenant Tool Re-Export

In `egress` mode, clients see Hangar's `hangar_*` meta-API (`hangar_list`,
`hangar_status`, etc.) and call back-end tools through it. In `front_door`
mode, external agents instead see **only the flat back-end tool names** (for
example `read_item`) — the clean tool surface they expect, with the meta-API
hidden.

This is done by re-registering the low-level `tools/list` and `tools/call`
handlers when the topology mode is `front_door`. Each request builds a
per-tenant `flat_name → (mcp_server, tool)` map, filtered to tools that are:

1. active (not withdrawn) for the caller's tenant, and
2. allowed for that tenant by the member-scope policy.

If two different back-end servers expose the same flat tool name, **both are
dropped** and a `flat_tool_name_collision` warning is logged — Hangar will not
route an ambiguous name to the wrong back end. Single-backend deployments never
hit this path. In `egress` mode the handlers are not replaced and the full
`hangar_*` surface is intact.

> Source: `src/mcp_hangar/fastmcp_server/flat_tool_projection.py`.

## OAuth Protected Resource Discovery (RFC 9728)

Hangar 1.3 acts as an OAuth 2.0 **resource server**. It **validates** bearer
tokens (JWT/OIDC) but it does **not** issue them, perform dynamic client
registration, or run any authorization-server logic. To let clients discover
where to obtain a token, Hangar implements RFC 9728 Protected Resource
Metadata.

### Metadata endpoint

When an OIDC issuer is configured, Hangar serves the metadata document at:

```text
GET /.well-known/oauth-protected-resource
```

The response advertises the resource server and its authorization server:

```json
{
  "resource": "https://hangar.example.com",
  "authorization_servers": ["https://auth.company.com"]
}
```

- `resource` — the public URI identifying this resource server. It comes from
  `auth.oidc.resource_uri` if set, otherwise it is derived from the request.
- `authorization_servers` — a single-element list containing
  `auth.oidc.issuer`.

This endpoint is unauthenticated (discovery must work without a token). If no
OIDC issuer is configured, it returns `404`.

### 401 challenge

When OIDC is active and a request fails authentication, the `401` response
carries a `WWW-Authenticate` header that points clients at the metadata URL:

```text
WWW-Authenticate: Bearer resource_metadata="https://hangar.example.com/.well-known/oauth-protected-resource", ApiKey
```

When OIDC is not configured, the challenge is simply `Bearer, ApiKey`.

```yaml
auth:
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    issuer: https://auth.company.com
    audience: mcp-hangar
    resource_uri: https://hangar.example.com   # advertised as "resource" in PRM
    tenant_claim: tenant_id
```

> Source: `src/mcp_hangar/auth/prm.py` (PRM body and `WWW-Authenticate`
> builders, `_PRM_PATH`),
> `src/mcp_hangar/server/lifecycle.py` (PRM route registration),
> `src/mcp_hangar/fastmcp_server/asgi.py` (401 challenge),
> `src/mcp_hangar/auth/config.py` (`resource_uri`).

## Full Config Example

```yaml
# config.yaml — front-door deployment

# Topology: face untrusted external agents, fail-closed per tenant.
tool_access:
  mode: front_door

# Validate JWTs from your IdP. Hangar is a resource server, not an issuer.
auth:
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    issuer: https://auth.company.com
    audience: mcp-hangar
    resource_uri: https://hangar.example.com
    tenant_claim: tenant_id

mcp_servers:
  payments:
    mode: remote
    endpoint: http://payments:8080/mcp
    description: "Payments backend"

    # Per-tenant tool access policy (server → member merge).
    tool_access:
      member:
        "tenant:a":
          deny_list: [refund]
        "tenant:b":
          allow_list: [charge, refund]

    # Config-declared tool withdrawals (effective = config OR runtime).
    tool_projection:
      withdrawn: [legacy_charge]
      tenant_overrides:
        "tenant:a":
          withdrawn: [refund]
```

## REST Endpoints

- `GET /.well-known/oauth-protected-resource` — RFC 9728 metadata.
- `POST /api/admin/tools/{server}/{tool}/withdraw` — runtime withdraw.
- `POST /api/admin/tools/{server}/{tool}/restore` — runtime restore.

For the full admin and auth surface, see [REST API](REST_API.md) and
[Authentication & Authorization](AUTHENTICATION.md).

## What's Next

Walk through a runnable end-to-end setup in the cookbook recipe
[16 — Front-Door Multi-Tenant](../cookbook/16-front-door-multi-tenant.md).
