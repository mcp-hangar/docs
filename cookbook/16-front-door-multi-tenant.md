# 16 -- Front-Door Multi-Tenant

> **Prerequisite:** [12 -- Auth & RBAC](12-auth-rbac.md)
> **You will need:** MCP Hangar 1.6.0, Docker, an OIDC issuer that mints JWTs with a `tenant_id` claim
> **Time:** 20 minutes
> **Adds:** Front-door topology mode, per-tenant tool access, runtime tool withdrawal, RFC 9728 discovery

## The Problem

You want to expose Hangar directly to external, untrusted agents -- not just
trusted callers on your internal network. That flips every default. An
unauthenticated request must be denied, not proxied. Each tenant should see and
call only the tools you allow them, not the full `hangar_*` meta-API. And when a
back-end tool misbehaves, you need to pull it for one tenant without restarting
or redeploying.

Hangar's `front_door` topology mode does exactly this: fail-closed
per-tenant tool governance, a flat per-tenant tool surface, and OAuth resource
server discovery.

## The Config

```yaml
# config.yaml -- Recipe 16: Front-Door Multi-Tenant

tool_access:
  mode: front_door                       # NEW: face untrusted callers, fail-closed

auth:                                     # validate JWTs; Hangar does not issue them
  enabled: true
  allow_anonymous: false
  oidc:                                   # NEW: OIDC resource server
    enabled: true
    issuer: https://auth.example.com      # your IdP
    audience: mcp-hangar
    resource_uri: https://hangar.example.com   # advertised by RFC 9728 metadata
    tenant_claim: tenant_id               # JWT claim -> CallerIdentity.tenant_id

mcp_servers:
  payments:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "Payments backend"

    tool_access:                          # NEW: per-tenant (member-scope) policy
      member:
        "tenant:a":
          deny_list: [refund]             # tenant:a cannot call refund
        "tenant:b":
          allow_list: [charge, refund]    # tenant:b limited to these two

    tool_projection:                      # NEW: config-declared withdrawals
      withdrawn: [legacy_charge]          # withdrawn for ALL tenants
      tenant_overrides:
        "tenant:a":
          withdrawn: [beta_tool]          # withdrawn for tenant:a only
```

Save this as `~/.config/mcp-hangar/config.yaml` or pass it with `--config`.

## Try It

1. Start Hangar in front-door mode

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 0.0.0.0 --port 8000
   ```

   With `tool_access.mode: front_door` and `auth.allow_anonymous: false`, every
   tool call now requires an authenticated tenant.

1. Discover the OAuth resource metadata (no token needed)

   ```bash
   curl -s http://localhost:8000/.well-known/oauth-protected-resource | jq
   ```

   Expected output:

   ```json
   {
     "resource": "https://hangar.example.com",
     "authorization_servers": ["https://auth.example.com"]
   }
   ```

   This is the RFC 9728 document. `resource` comes from
   `auth.oidc.resource_uri`; `authorization_servers` lists `auth.oidc.issuer`.

1. Confirm unauthenticated calls are denied (fail-closed)

   ```bash
   curl -s -i http://localhost:8000/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | grep -i "^HTTP\|^WWW-Authenticate"
   ```

   Expected output:

   ```text
   HTTP/1.1 401 Unauthorized
   WWW-Authenticate: Bearer resource_metadata="https://hangar.example.com/.well-known/oauth-protected-resource", ApiKey
   ```

   The `WWW-Authenticate` header points the agent back at the discovery
   endpoint so it knows where to get a token.

1. Call a tool as a tenant

   Obtain a JWT from your IdP whose `tenant_id` claim is `tenant:b`, then list
   tools. In front-door mode external agents see flat back-end tool names, not
   the `hangar_*` meta-API.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_B_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq '.result.tools[].name'
   ```

   Expected output for `tenant:b` (allow_list of `charge`, `refund`):

   ```text
   "charge"
   "refund"
   ```

   `tenant:a` would instead see `charge` but not `refund` (denied) or
   `beta_tool` (withdrawn for that tenant).

1. Withdraw a tool at runtime for one tenant

   Pull `refund` for `tenant:b` without touching config. This needs an admin
   key (the `lifecycle` action on the `mcp_servers` resource).

   ```bash
   curl -s -X POST \
     http://localhost:8000/api/admin/tools/payments/refund/withdraw \
     -H "X-API-Key: <admin-key>" \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "tenant:b"}' | jq
   ```

   Expected output:

   ```json
   {"withdrawn": true, "mcp_server": "payments", "tool": "refund", "tenant_id": "tenant:b"}
   ```

   Re-running the `tools/list` from step 4 as `tenant:b` now returns only
   `charge`.

1. Restore the tool

   ```bash
   curl -s -X POST \
     http://localhost:8000/api/admin/tools/payments/refund/restore \
     -H "X-API-Key: <admin-key>" \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "tenant:b"}' | jq
   ```

   Expected output:

   ```json
   {"restored": true, "mcp_server": "payments", "tool": "refund", "tenant_id": "tenant:b"}
   ```

   Omitting `tenant_id` (or sending `null`) withdraws/restores globally for all
   tenants instead of one.

## What Just Happened

Setting `tool_access.mode: front_door` flips Hangar's topology from
trusted-egress to untrusted-front-door. The access resolver now applies a
fail-closed default: a caller with no tenant identity is denied every tool
before any server- or group-level policy is even consulted. That is what makes
the unauthenticated `tools/list` in step 3 return `401`.

The tenant comes from the JWT `tenant_claim` (default `tenant_id`), which
Hangar reads into `CallerIdentity.tenant_id` and uses to resolve the
member-scope policy on the live call path. The server-level policy is merged
with the matching `tool_access.member` entry, so `tenant:a` and `tenant:b` get
different effective tool sets from the same back end.

In front-door mode Hangar also re-exports a **flat** tool surface: external
agents see clean back-end tool names (`charge`, `refund`) instead of the
`hangar_*` meta-API, filtered per request to the tools that are active and
allowed for that tenant. (If two back-end servers expose the same flat name,
both are dropped to avoid routing ambiguity.)

Tool withdrawal has two independent overlays. Config-declared withdrawals
(`tool_projection.withdrawn` / `tenant_overrides`) survive reloads. Runtime
withdrawals via the admin API survive reloads too, and `restore` only clears the
runtime overlay. The effective state is `config OR runtime` -- a tool is
withdrawn if either says so.

Finally, the `/.well-known/oauth-protected-resource` endpoint and the
`WWW-Authenticate` challenge make Hangar a discoverable OAuth resource server.
Hangar **validates** the JWTs your IdP issues; it never issues tokens itself.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tool_access.mode` | string | `egress` | Topology mode: `egress` or `front_door` |
| `tool_access.member.<tenant>.allow_list` | list | `[]` | Tools this tenant may call |
| `tool_access.member.<tenant>.deny_list` | list | `[]` | Tools this tenant may not call |
| `tool_projection.withdrawn` | list | `[]` | Tools withdrawn for all tenants |
| `tool_projection.tenant_overrides.<tenant>.withdrawn` | list | `[]` | Tools withdrawn for one tenant |
| `auth.oidc.enabled` | bool | `false` | Enable OIDC/JWT validation |
| `auth.oidc.issuer` | string | `""` | OIDC issuer; advertised in metadata |
| `auth.oidc.resource_uri` | string | `""` | Public URI advertised as `resource` |
| `auth.oidc.tenant_claim` | string | `tenant_id` | JWT claim mapped to `tenant_id` |

## What's Next

For the conceptual model, egress-vs-front-door comparison, and the full
endpoint and config reference, see the
[Front-Door Mode](../guides/FRONT_DOOR.md) guide.

To trust more than one authorization server and bind accepted token audiences
to your resource URI (RFC 8707), continue with
[17 -- Multi-Issuer Front Door](17-multi-issuer-front-door.md).
