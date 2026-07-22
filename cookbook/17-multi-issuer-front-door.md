# 17 -- Multi-Issuer Front Door

> **Prerequisite:** [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md)
> **You will need:** MCP Hangar 1.6.0, two OIDC issuers that mint JWTs with a `tenant_id` claim and `aud` set to your resource URI
> **Time:** ~15 minutes
> **Adds:** Multi-issuer OAuth trust, RFC 8707 resource-bound audience, RFC 9728 multi-issuer discovery

## The Problem

Recipe 16 fronted untrusted agents that all came from a single IdP. Real SaaS is
messier: each customer brings their own identity provider. Customer A authenticates
agents through Keycloak; Customer B uses Auth0. You still want **one** Hangar
front door, but it now has to trust two authorization servers at once -- and it
must not silently accept a token from some third issuer that nobody onboarded.

A single `auth.oidc.issuer` cannot express that. You need a list of trusted
issuers, each with its own JWKS, and a way to prove -- auditably -- that every
accepted token was minted *for this Hangar* and not replayed from another
resource. Hangar 1.4 adds a multi-issuer trust list plus RFC 8707 audience
binding: when you set `auth.oidc.resource_uri`, the value you advertise as the
RFC 9728 `resource` is the exact value enforced as each token's `aud`.

## The Config

```yaml
# config.yaml -- Recipe 17: Multi-Issuer Front Door

tool_access:
  mode: front_door                         # face untrusted callers, fail-closed

auth:                                       # validate JWTs; Hangar does not issue them
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    resource_uri: https://hangar.example.com   # NEW: advertised AND enforced as aud (RFC 8707)
    tenant_claim: tenant_id                 # default claim -> CallerIdentity.tenant_id
    issuers:                                # NEW: trust list; overrides legacy single `issuer`
      - issuer: https://issuer-a.example.com      # Customer A (e.g. Keycloak)
        audience: https://hangar.example.com      # ignored while resource_uri is set
        jwks_uri: https://issuer-a.example.com/jwks
      - issuer: https://issuer-b.example.com      # Customer B (e.g. Auth0)
        audience: https://hangar.example.com      # ignored while resource_uri is set
        jwks_uri: https://issuer-b.example.com/jwks
        groups_claim: roles                 # per-issuer override; tenant_claim inherits top-level

mcp_servers:
  payments:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "Payments backend"

    tool_access:                            # per-tenant (member-scope) policy
      member:
        "tenant:a":
          allow_list: [charge]
        "tenant:b":
          allow_list: [charge, refund]
```

Save this as `~/.config/mcp-hangar/config.yaml` or pass it with `--config`.

Because `resource_uri` is set, each issuer's `audience` is overridden at
validation time: every token -- from issuer-a or issuer-b -- must carry
`aud: https://hangar.example.com`. The per-issuer `audience` lines are kept
documented above but are inert until you remove `resource_uri`.

## Try It

1. Start Hangar in front-door mode

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 0.0.0.0 --port 8000
   ```

   With `tool_access.mode: front_door` and `auth.allow_anonymous: false`, every
   tool call requires an authenticated tenant from one of the trusted issuers.

1. Discover the OAuth resource metadata (no token needed)

   ```bash
   curl -s http://localhost:8000/.well-known/oauth-protected-resource | jq
   ```

   Expected output:

   ```json
   {
     "resource": "https://hangar.example.com",
     "authorization_servers": [
       "https://issuer-a.example.com",
       "https://issuer-b.example.com"
     ]
   }
   ```

   This is the RFC 9728 document. `resource` comes from
   `auth.oidc.resource_uri`; `authorization_servers` lists **every** entry in
   `auth.oidc.issuers`, not a single one. A client discovers both authorization
   servers it may legitimately get a token from.

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
   endpoint. (Without OIDC configured the challenge would be just
   `Bearer, ApiKey`.)

1. Call a tool as a tenant from issuer-a

   Obtain a JWT from Customer A's IdP whose `iss` is
   `https://issuer-a.example.com`, `aud` is `https://hangar.example.com`, and
   `tenant_id` is `tenant:a`, then list tools.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $ISSUER_A_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq '.result.tools[].name'
   ```

   Expected output for `tenant:a` (allow_list of `charge`):

   ```text
   "charge"
   ```

1. Call a tool as a tenant from issuer-b

   A JWT from Customer B's IdP -- different `iss`
   (`https://issuer-b.example.com`), different JWKS -- is validated the same
   way. With `aud: https://hangar.example.com` and `tenant_id: tenant:b`:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $ISSUER_B_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq '.result.tools[].name'
   ```

   Expected output for `tenant:b` (allow_list of `charge`, `refund`):

   ```text
   "charge"
   "refund"
   ```

   One front door, two authorization servers, two tenants -- each resolved to
   its own member-scope policy from the same back end.

1. Reject a token from an unknown issuer (fail-closed)

   Mint a structurally valid JWT from an issuer you never onboarded -- say
   `https://rogue.example.com` -- and try to use it.

   ```bash
   curl -s -i http://localhost:8000/mcp \
     -H "Authorization: Bearer $ROGUE_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | grep -i "^HTTP\|Untrusted"
   ```

   Expected output:

   ```text
   HTTP/1.1 401 Unauthorized
   ```

   The request is rejected with a `401` (never a `500`) before the token reaches
   any signature validator -- the `iss` claim is not in the trust list, so there
   is no JWKS to even check it against. The same fate awaits a token with a
   missing, empty, or non-string `iss`. Critically, the error does **not**
   enumerate which issuers *are* trusted: an attacker probing the front door
   learns nothing about your trust list.

## What Just Happened

`auth.oidc.issuers` replaces the single-issuer model with an ordered trust list.
It takes precedence over the legacy top-level `auth.oidc.issuer`, so once a list
is present Hangar trusts exactly those entries and nothing else. Each entry
carries its own `jwks_uri`, which is how two completely independent IdPs
(Keycloak, Auth0) can be validated side by side without sharing keys.

Validation is routed by the `iss` claim. When a bearer token arrives, Hangar
first reads `iss` and looks it up in the trust list. If `iss` is missing, empty,
not a string, or not a configured issuer, the request fails closed with a `401`
and the token never reaches a signature or audience check -- that is what makes
step 6 a clean rejection rather than a crash. The set of trusted issuers is
deliberately kept out of the error response.

The audience binding is the audit story. Because `auth.oidc.resource_uri` is set
to `https://hangar.example.com`, every token's `aud` claim is validated against
that single URI regardless of each issuer entry's own `audience` (RFC 8707
resource indicators). The value you publish in the RFC 9728 metadata as
`resource` is therefore the exact value you enforce as `aud`. A token Customer A
minted for some other API -- even from a trusted issuer -- will not be accepted
here, and the discovery document, the `WWW-Authenticate` challenge, and the
enforced audience all name the same resource URI. Remove `resource_uri` and
validation falls back to each issuer's configured `audience` instead.

Per-issuer claim mappings inherit from the top level. issuer-b overrides
`groups_claim: roles`, but it omits `tenant_claim`, so it inherits
`tenant_claim: tenant_id` from `auth.oidc`. Both issuers therefore resolve the
tenant from `tenant_id` into `CallerIdentity.tenant_id`, which the front-door
access resolver uses to apply the member-scope policy -- exactly as in Recipe
16. Hangar remains a resource server throughout: it **validates** these JWTs, it
does not issue them, mint refresh tokens, or perform dynamic client
registration.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tool_access.mode` | string | `egress` | Topology mode: `egress` or `front_door` |
| `auth.oidc.enabled` | bool | `false` | Enable OIDC/JWT validation |
| `auth.oidc.resource_uri` | string | `""` | Public URI advertised as `resource`; also enforced as JWT `aud` when set |
| `auth.oidc.issuers` | list | `[]` | Multi-issuer trust entries; overrides legacy `auth.oidc.issuer` |
| `auth.oidc.issuers[].issuer` | string | -- | Trusted `iss` value matched against the token |
| `auth.oidc.issuers[].audience` | string | -- | Expected `aud` for this issuer; ignored while `resource_uri` is set |
| `auth.oidc.issuers[].jwks_uri` | string | -- | JWKS endpoint used to verify this issuer's signatures |
| `auth.oidc.tenant_claim` | string | `tenant_id` | JWT claim mapped to `tenant_id`; inherited by issuer entries that omit it |

## What's Next

For the full OIDC configuration schema, claim mappings, and multi-issuer trust
semantics, see the [Authentication & Authorization](../guides/AUTHENTICATION.md)
guide. For the front-door topology model, fail-closed access resolution, and the
RFC 9728 / RFC 8707 discovery endpoints, see the
[Front-Door Mode](../guides/FRONT_DOOR.md) guide.
