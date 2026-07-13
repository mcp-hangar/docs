# 20 -- External Multi-Tenant OIDC Front Door

> **Prerequisite:** [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md)
> **You will need:** MCP Hangar 1.4.0, Docker (for a local, test-only Keycloak), `jq`, `curl`
> **Time:** ~30 minutes
> **Adds:** An end-to-end external OIDC front door -- local Keycloak dev realm, two tenants with distinct tool surfaces, cross-tenant isolation proof, RFC 9728 discovery, and token-validation troubleshooting

## The Problem

Recipe 16 showed the front-door primitives against an abstract IdP. This recipe
walks the whole thing end to end with a **real, local** OpenID Provider so you
can run it on your laptop and *prove* the guarantees: two external tenants
authenticate through OIDC, are identified per tenant from a JWT claim, and each
sees and invokes only the tools its tenant is allowed. Neither tenant can observe
the other's tools, and an unauthenticated or wrong-audience caller is rejected
before it reaches a back end.

Hangar is an OAuth **Resource Server** here. It **validates** the JWTs your
identity provider issues -- signature, issuer, audience, expiry -- and maps the
tenant claim to an effective tenant. It never issues tokens, mints refresh
tokens, or performs dynamic client registration; that is Keycloak's job.

> **Test-only Keycloak.** The Keycloak realm, clients, users, and passwords
> below are a *disposable local development profile*. The realm is created fresh
> at container start, secrets come from environment variables you set locally,
> and token lifetimes are deliberately short. Never import a production realm
> into this profile, never commit a client secret, and never reuse these
> throwaway passwords anywhere real.

## The Config

```yaml
# config.yaml -- Recipe 20: External Multi-Tenant OIDC Front Door

tool_access:
  mode: front_door                          # opt-in; unauthenticated callers denied

auth:                                        # validate JWTs; Hangar does not issue them
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    issuer: http://localhost:8080/realms/hangar-dev    # local test-only Keycloak realm
    jwks_uri: http://localhost:8080/realms/hangar-dev/protocol/openid-connect/certs
    resource_uri: http://localhost:8000                # advertised (RFC 9728) AND enforced as aud
    audience: http://localhost:8000                    # inert while resource_uri is set; kept explicit
    tenant_claim: tenant_id                            # JWT claim -> CallerIdentity.tenant_id

mcp_servers:
  payments:
    mode: remote
    endpoint: http://localhost:8081/mcp
    description: "Payments backend"

    tool_access:                            # per-tenant (member-scope) policy
      member:
        "tenant:acme":
          allow_list: [charge]              # acme may only charge
        "tenant:globex":
          allow_list: [charge, refund]      # globex may charge and refund

  billing:
    mode: remote
    endpoint: http://localhost:8082/mcp
    description: "Billing backend"

    tool_access:
      member:
        "tenant:globex":
          allow_list: [invoice]             # only globex sees the billing tool
```

Save this as `~/.config/mcp-hangar/config.yaml` or pass it with `--config`.

Because `resource_uri` is set, every accepted token's `aud` claim is validated
against `http://localhost:8000` (RFC 8707 resource indicators): the value Hangar
advertises as the RFC 9728 `resource` is the exact value it enforces as `aud`.

## Bootstrap the Local Keycloak (test-only)

Run a throwaway Keycloak in development mode. Set the admin and realm secrets in
your shell first so nothing sensitive is written to disk:

```bash
export KC_BOOTSTRAP_ADMIN_USERNAME=admin
export KC_BOOTSTRAP_ADMIN_PASSWORD=dev-only-change-me   # local throwaway, not for prod

docker run --rm -p 8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD \
  quay.io/keycloak/keycloak:26.0 start-dev
```

Then create a **test-only** realm `hangar-dev`, two confidential clients, and two
users -- one per tenant -- with a protocol mapper that puts a hardcoded
`tenant_id` claim into each user's access token. Using the admin CLI baked into
the image:

```bash
KC=http://localhost:8080

# Authenticate the admin CLI (session token is short-lived).
docker exec -i keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server "$KC" --realm master \
  --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"

# Test-only realm with short token lifetime (no long-lived credentials).
docker exec -i keycloak /opt/keycloak/bin/kcadm.sh create realms \
  -s realm=hangar-dev -s enabled=true -s accessTokenLifespan=300

# One confidential client per tenant (direct-grant enabled for the demo).
for T in acme globex; do
  docker exec -i keycloak /opt/keycloak/bin/kcadm.sh create clients -r hangar-dev \
    -s clientId="agent-$T" -s enabled=true -s publicClient=false \
    -s directAccessGrantsEnabled=true \
    -s 'defaultClientScopes=["hangar-audience"]'
done
```

Two things make the tokens usable by Hangar:

1. **The `tenant_id` claim.** Add a hardcoded-claim protocol mapper to each
   client (`tenant:acme` for the acme client, `tenant:globex` for the globex
   client) so every access token carries `tenant_id`. Hangar reads this into
   `CallerIdentity.tenant_id`; it never trusts a client-supplied tenant.

1. **The `aud` claim.** Add an audience mapper (client scope `hangar-audience`
   above) that sets `aud` to `http://localhost:8000` -- the same value as
   `auth.oidc.resource_uri`. A token minted for any other audience is rejected.

Create the two demo users (throwaway passwords, test realm only):

```bash
docker exec -i keycloak /opt/keycloak/bin/kcadm.sh create users -r hangar-dev \
  -s username=acme-agent -s enabled=true
docker exec -i keycloak /opt/keycloak/bin/kcadm.sh set-password -r hangar-dev \
  --username acme-agent --new-password dev-only-acme

docker exec -i keycloak /opt/keycloak/bin/kcadm.sh create users -r hangar-dev \
  -s username=globex-agent -s enabled=true
docker exec -i keycloak /opt/keycloak/bin/kcadm.sh set-password -r hangar-dev \
  --username globex-agent --new-password dev-only-globex
```

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
     "resource": "http://localhost:8000",
     "authorization_servers": ["http://localhost:8080/realms/hangar-dev"]
   }
   ```

   This is the RFC 9728 Protected Resource Metadata document. `resource` comes
   from `auth.oidc.resource_uri`; `authorization_servers` lists your issuer. An
   agent uses this to discover where it must go to get a token.

1. Confirm anonymous calls are denied (fail-closed)

   ```bash
   curl -s -i http://localhost:8000/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | grep -i "^HTTP\|^WWW-Authenticate"
   ```

   Expected output:

   ```text
   HTTP/1.1 401 Unauthorized
   WWW-Authenticate: Bearer resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource", ApiKey
   ```

   The `WWW-Authenticate` challenge points the agent back at the discovery
   endpoint, so a well-behaved client can bootstrap into the OAuth flow.

1. Get a token for each tenant

   Use Keycloak's direct-grant endpoint (demo shortcut; a real agent would run
   the standard OAuth flow). Substitute each client's secret:

   ```bash
   token() {
     curl -s http://localhost:8080/realms/hangar-dev/protocol/openid-connect/token \
       -d grant_type=password -d "client_id=agent-$1" \
       -d "client_secret=$2" -d "username=$1-agent" -d "password=dev-only-$1" \
       | jq -r .access_token
   }
   ACME_JWT=$(token acme "$ACME_CLIENT_SECRET")
   GLOBEX_JWT=$(token globex "$GLOBEX_CLIENT_SECRET")
   ```

1. Each tenant sees a different, flat tool surface

   In front-door mode external agents see flat back-end tool names, not the
   `hangar_*` control-plane API. List tools as acme:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $ACME_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq -S '.result.tools[].name'
   ```

   Expected for `tenant:acme` (allow_list of `charge` on `payments` only):

   ```text
   "charge"
   ```

   Now list tools as globex:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $GLOBEX_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq -S '.result.tools[].name'
   ```

   Expected for `tenant:globex` (`charge`, `refund` on `payments`; `invoice` on
   `billing`):

   ```text
   "charge"
   "invoice"
   "refund"
   ```

1. The same isolation holds on `server/discover`

   The SEP-2575 `server/discover` entry point is scoped to the caller's tenant
   from the identity context, exactly like `tools/list`:

   ```bash
   curl -s http://localhost:8000/server/discover \
     -H "Authorization: Bearer $ACME_JWT" | jq '.tools[].name'
   ```

   acme sees only `charge` here too -- one round-trip advertises the tenant's
   allowed tools without a separate `tools/list`.

1. Prove tenants cannot observe or invoke each other's tools

   `invoice` and `refund` never appear in acme's list. Confirm acme also cannot
   *call* them even by guessing the name:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $ACME_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"refund","arguments":{}},"id":1}' \
     | jq '.error.code // .result.isError'
   ```

   Expected output:

   ```text
   -32601
   ```

   `refund` is absent from acme's per-tenant map, so the call is rejected with
   `-32601` (method not found) and no back end is ever contacted. The projection
   hides the tool *and* the call path refuses it -- see below.

1. Reject a wrong-audience / unknown-issuer token (fail-closed)

   A structurally valid JWT minted for another audience -- or by an issuer you
   never configured -- is rejected. For example, a token whose `aud` is not
   `http://localhost:8000`:

   ```bash
   curl -s -i http://localhost:8000/mcp \
     -H "Authorization: Bearer $WRONG_AUD_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | grep -i "^HTTP"
   ```

   Expected output:

   ```text
   HTTP/1.1 401 Unauthorized
   ```

   Audience and issuer are checked during validation. A token from an issuer
   that is not configured never reaches a signature check at all -- there is no
   JWKS to verify it against -- and the error does not enumerate what *is*
   trusted.

1. Withdraw a tool globally, then per tenant

   Pull `refund` for **all** tenants at runtime (needs an admin key with the
   `lifecycle` action on `mcp_servers`):

   ```bash
   curl -s -X POST \
     http://localhost:8000/api/admin/tools/payments/refund/withdraw \
     -H "X-API-Key: <admin-key>" \
     -H "Content-Type: application/json" \
     -d '{}' | jq
   ```

   Expected output:

   ```json
   {"withdrawn": true, "mcp_server": "payments", "tool": "refund", "tenant_id": null}
   ```

   Sending `{}` (no `tenant_id`) withdraws globally; globex's `tools/list` no
   longer includes `refund`. Add `{"tenant_id": "tenant:globex"}` to scope a
   withdrawal to one tenant, and `restore` with the same body to reverse it.

## What Just Happened

Setting `tool_access.mode: front_door` flips Hangar from trusted-egress to an
untrusted front door with a fail-closed default: a caller with **no** tenant
identity is denied every tool before any server- or group-level policy is even
consulted. That is why the anonymous `tools/list` in step 3 returns `401` rather
than an empty list.

The tenant is never client-supplied. It comes from the JWT `tenant_claim`
(default `tenant_id`), which Hangar reads into `CallerIdentity.tenant_id` after
validating the token, and then uses to resolve the member-scope policy. `acme`
and `globex` get different effective tool sets from the same back ends because
their tenant IDs select different `tool_access.member` entries.

There are **two** layers, and they are not the same thing:

- **Projection is a UX / discovery view.** The flat `tools/list` and
  `server/discover` surfaces are built per request from the tenant's allowed,
  non-withdrawn tools. This is what an agent *sees*. Two tenants never share a
  view: acme's map has no `refund` or `invoice` entry to begin with.
- **The call path is authoritative.** Every invocation is routed through the
  same enforcement path (resolver policy check, then withdrawal check) regardless
  of what the projection showed. Even a tool guessed by name (step 8) is
  re-checked and refused. A tool that was withdrawn between list and call is
  denied at call time, and the back end is never invoked. Discovery hides tools;
  authorization enforces the decision.

RFC 9728 makes the front door discoverable: the
`/.well-known/oauth-protected-resource` document and the `WWW-Authenticate`
challenge advertise the resource URI and issuer. Because `resource_uri` is set,
that same URI is enforced as each token's `aud` (RFC 8707), so a token minted for
another API is not accepted here. To trust more than one issuer at once, add an
`auth.oidc.issuers` trust list as in
[17 -- Multi-Issuer Front Door](17-multi-issuer-front-door.md).

Throughout, Hangar stays a Resource Server. Keycloak issues and signs the
tokens; Hangar only validates them.

## Troubleshooting Token Validation

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `401`, message `Invalid JWT audience` | token `aud` does not equal `auth.oidc.resource_uri` | add/repair the Keycloak audience mapper so `aud` is `http://localhost:8000` |
| `401`, message `Untrusted JWT issuer` | token `iss` is not the configured issuer | align `auth.oidc.issuer` with the realm URL in the token's `iss` |
| `401`, message `JWT token has expired` | clock skew or long-lived token | shorten `accessTokenLifespan`; mint a fresh token |
| `401` even with a valid-looking token, log `oidc_config_incomplete` | `issuer`/`audience` missing at startup | set both (or `resource_uri`) before enabling OIDC |
| Token accepted but tenant is empty / denied everywhere | `tenant_id` claim absent from the token | add the hardcoded-claim mapper; confirm the claim name matches `tenant_claim` |

Token lifetime is also capped server-side: Hangar rejects a token whose
`exp - iat` exceeds `max_token_lifetime_seconds` (default 3600), overridable via
the `MCP_JWT_MAX_TOKEN_LIFETIME` environment variable. Decode a token locally
with `jq` to inspect its claims:

```bash
echo "$ACME_JWT" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{iss, aud, exp, tenant_id}'
```

## Audit Evidence

Every decision is observable, which is what makes the two-tenant proof auditable:

- **HTTP responses are the first-line evidence.** Anonymous and wrong-audience
  calls return `401` with an `authentication_failed` body; an authenticated but
  disallowed call returns a JSON-RPC `-32601` (projection miss) or a
  `CallToolResult` with `isError: true` (denied at the enforcement path). No
  denied call reaches a back end.
- **Structured logs** record the wiring and the per-request surface: startup
  emits `oidc_auth_enabled` and `standalone_member_tool_access_policy_set` (one
  per tenant policy loaded); each `server/discover` call logs `server_discover`
  with the resolved `tenant_id` and tool count. Correlate these to show that
  acme and globex resolved to different surfaces from the same server.

Run the two-tenant walkthrough, capture the `tools/list` output for each token
plus the matching log lines, and you have a reproducible demonstration that the
tenants are isolated and that access decisions fail closed.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tool_access.mode` | string | `egress` | Topology mode: `egress` or `front_door` |
| `auth.enabled` | bool | `false` | Master switch for authentication |
| `auth.allow_anonymous` | bool | `false` | If `true`, unauthenticated requests run as anonymous |
| `auth.oidc.enabled` | bool | `false` | Enable OIDC/JWT validation |
| `auth.oidc.issuer` | string | `""` | Trusted `iss`; advertised as an authorization server |
| `auth.oidc.jwks_uri` | string | auto | JWKS endpoint; auto-discovered from `issuer` if unset |
| `auth.oidc.audience` | string | `""` | Expected `aud`; inert while `resource_uri` is set |
| `auth.oidc.resource_uri` | string | `""` | Public URI advertised as `resource`; also enforced as `aud` when set |
| `auth.oidc.tenant_claim` | string | `tenant_id` | JWT claim mapped to `CallerIdentity.tenant_id` |
| `mcp_servers.<id>.tool_access.member.<tenant>.allow_list` | list | `[]` | Tools this tenant may call on that server |
| `mcp_servers.<id>.tool_access.member.<tenant>.deny_list` | list | `[]` | Tools this tenant may not call on that server |

## What's Next

For multi-issuer trust (a distinct IdP per customer) and RFC 8707 audience
binding across issuers, continue with
[17 -- Multi-Issuer Front Door](17-multi-issuer-front-door.md). For the
conceptual model, the egress-vs-front-door comparison, and the full endpoint and
config reference, see the [Front-Door Mode](../guides/FRONT_DOOR.md) guide; for
the OIDC schema and claim mappings, see the
[Authentication & Authorization](../guides/AUTHENTICATION.md) guide.
