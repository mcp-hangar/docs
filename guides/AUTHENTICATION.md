# Authentication & Authorization

MCP-Hangar supports production-grade authentication (AuthN) and authorization (AuthZ) for secure multi-tenant access control.

## Quick Start

Authentication is **opt-in** and disabled by default. To enable it:

### 1. Enable in Configuration

```yaml
# config.yaml
auth:
  enabled: true  # Enable authentication
  allow_anonymous: false  # Require authentication for all requests

  storage:
    driver: sqlite        # durable; `mcp-hangar auth bootstrap-admin` needs it
    path: data/auth.db

  api_key:
    enabled: true
    header_name: X-API-Key
```

The storage driver defaults to `memory`, and `bootstrap-admin` refuses a
`memory` backend (`Auth storage driver 'memory' is not durable`), so a deployment
that relies on API keys needs `sqlite` or `postgresql` before it can get its
first key.

### 2. Create an API Key

`principal_id` and `name` are required. Since 2.34.2 a body that is not a JSON
object answers `400` with `{"error": "invalid_body", ...}`, and one without a
required field answers `400` with `{"error": "missing_fields", "detail":
"required field(s) absent: ..."}`. Before 2.34.2 either was a `500`.

```bash
curl -X POST http://localhost:8000/api/auth/keys \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "service:my-app",
    "name": "My App Key"
  }'

# Response:
# {
#   "key_id": "N3xQ...",
#   "raw_key": "mcp_aBcDeFgHiJkLmNoPqRsTuVwXyZ...",
#   "principal_id": "service:my-app",
#   "name": "My App Key",
#   "expires_at": null,
#   "warning": "Save this key now - it cannot be retrieved later!"
# }
```

There is no `role` field on this route -- a key carries a principal, and roles
are assigned to the principal separately (see below).

Getting the **first** admin key is a different problem: `/api/auth/**` requires
an admin principal with no carve-out, so nothing can mint it over HTTP.
`mcp-hangar auth bootstrap-admin` is the way in. It grants the admin role and
mints a key in one one-shot claim, and `--show-key` decides whether that key's
secret is printed -- unnecessary for an OIDC principal that authenticates on its
own identity, and required when API keys are all you have, where *since 2.5.0*
omitting it is refused rather than silently spending the claim. See
[recipe 12](../cookbook/12-auth-rbac.md) for what that means in practice.

### 3. Use the API Key

An API key travels only in the configured header. `Authorization: Bearer`
carries a JWT, and an API key sent there is refused with `401`. The scheme
name is matched without regard to case, so `bearer <jwt>` is read as a JWT too;
before 2.34.2 only `Bearer` was, and any other spelling counted as no
credential.

```bash
# HTTP mode
curl -H "X-API-Key: mcp_aBcDeFgHiJkLmNoPqRsTuVwXyZ..." \
  http://localhost:8000/mcp

# Or in MCP client configuration
{
  "headers": {
    "X-API-Key": "mcp_aBcDeFgHiJkLmNoPqRsTuVwXyZ..."
  }
}
```

## Authentication Methods

### API Key Authentication

Simple key-based authentication. Keys are:

- Prefixed with `mcp_` for easy identification
- Stored as SHA-256 hashes (never in plaintext)
- Support expiration and revocation

```yaml
auth:
  api_key:
    enabled: true
    header_name: X-API-Key  # Can be customized
```

### JWT/OIDC Authentication

For SSO / OIDC integration with MCP servers like Okta, Auth0, Azure AD:

```yaml
auth:
  oidc:
    enabled: true
    issuer: https://auth.company.com
    audience: mcp-hangar
    # Claim mappings (optional)
    groups_claim: groups
    tenant_claim: org_id
```

Since MCP Hangar 1.4.0, front-door deployments can trust multiple OIDC issuers
and bind accepted JWT audiences to the public resource URI.

```yaml
auth:
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    resource_uri: https://hangar.example.com
    tenant_claim: tenant_id
    issuers:
      - issuer: https://issuer-a.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-a.example.com/jwks
        allowed_tenants: [team-a]
      - issuer: https://issuer-b.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-b.example.com/jwks
        groups_claim: roles
        allowed_tenants: [team-b]
```

When `resource_uri` is set, Hangar validates each token's `aud` claim against
that URI, regardless of the issuer entry's `audience`. This makes the value
advertised as RFC 9728 `resource` the same value enforced as the RFC 8707
resource indicator. Without `resource_uri`, each issuer uses its own configured
`audience`.

`auth.oidc.issuers` takes precedence over the legacy top-level `issuer` field.
Per-issuer entries inherit omitted claim mappings from top-level `oidc.*` fields.
Tokens with a missing, empty, non-string, or untrusted `iss` claim fail closed.

#### Binding each issuer to its tenants

*Since 2.34.2.* Without a binding, every trusted issuer may sign a token naming
any tenant, and a `sub` or group it asserts is the same principal as the one
another issuer asserts. `allowed_tenants` on an `issuers` entry closes the first
half:

- A token from a bound issuer is refused with `401` unless its tenant claim is a
  string in the list. A token that names no tenant is refused too.
- The list must hold at least one non-empty string. An empty list, a bare
  string, or the key with no value refuses the configuration rather than leaving
  the issuer unbound.
- The key is per issuer. Set at the top level of `auth.oidc` it refuses the
  configuration.
- With two or more issuers and any of them unbound, boot logs one
  `oidc_issuers_not_bound_to_tenants` warning naming them. A single issuer needs
  no binding and logs nothing.

The binding confines tenant-scoped roles only. A role assigned at scope `global`
to a subject or to `group:<name>` still reaches a token carrying that subject
or group from any trusted issuer. With more than one identity provider, grant
OIDC users and groups only `tenant:<id>` roles, and do not list one tenant under
two issuers.

## Authorization (RBAC)

### Built-in Roles

| Role | Description | Permissions |
| ------ | ------------- | ------------- |
| `admin` | Full access | Everything (`*:*`) |
| `kubernetes-operator` | Role for the Kubernetes operator's API key: register, start and deregister servers, deliver egress policy | `mcp_servers:read/write/lifecycle`, `mcp_servers:peer_identity`, `policy:read`, `policy:write` |
| `provider-admin` | Manage servers, deliver egress policy, invoke tools | `providers:read/write/lifecycle`, `mcp_servers:local_launch`, `policy:read`, `policy:write`, `group:*`, `discovery:read/trigger/approve`, `tool:invoke`, `tool:list`, `metrics:read`, **`approval:read`**, **`approval:resolve`** |
| `developer` | Use tools, start servers on demand, register `remote` servers | `provider:read/list/start/load/load_verified/unload`, `providers:read/write/lifecycle`, `tool:invoke/list`, `group:read/list`, `discovery:read` |
| `viewer` | Read-only | `providers:read`, `provider:read/list`, `tool:list`, `metrics:read`, `group:read/list`, `discovery:read` |
| `auditor` | Audit logs and read-only oversight | `audit:read`, `metrics:read`, `provider:list`, `group:list`, `discovery:read`, **`approval:read`** |
| `service-account` | Default for service accounts — invoke tools | `provider:read/list`, `tool:invoke/list` |

Role names are exactly as shown. `providers:read/write/lifecycle` are the names
the permission registry uses; the API reports them, and authorizes against
them, as `mcp_servers:read/write/lifecycle`. The name `mcp_server_admin` appeared in an
earlier revision of this table and does not exist — the role is
`provider-admin`, which kept its original name through the provider→MCP-server
rename.

The `provider:*` family is the pre-rename vocabulary and the REST API authorizes
against `mcp_servers:*` instead, so those entries grant nothing over the API.
Until core 2.29.1 `provider-admin` carried only those entries plus
`providers:read` and `policy:write`: it could read servers and deliver compiled
egress policy but could not register, start or stop a server. From 2.29.1 it
holds `providers:write` and `providers:lifecycle` (reported as
`mcp_servers:write` and `mcp_servers:lifecycle`) in place of the dead entries,
so a key on it now registers, reconfigures, starts, stops and removes servers.
It still has no `config:reload` and no `admin:*`.

#### `mcp_servers:local_launch`

*Since 2.34.2.* A `subprocess`, `docker` or `container` server runs a command
or image the caller chose on the gateway's own host, so registering one over
REST needs more than `mcp_servers:write`. `mcp_servers:local_launch` is also
required for:

- `POST /api/mcp_servers/` with any `mode` other than `remote` (a mode Hangar
  does not recognise counts as local here);
- `PUT` or `PATCH /api/mcp_servers/{id}` that sets `env` on a server that is not
  `remote`.

Without it these answer `403`. Registering a `remote` server, and every other
field of an update, still need only `mcp_servers:write`. `admin` and
`provider-admin` hold the permission; `developer` and `kubernetes-operator` do
not (the operator registers only `remote` servers). The check runs on the REST
request only: a local server a developer registered before 2.34.2 still loads
at boot and starts as before. With authentication off every caller passes it,
as every other check. To let a principal keep registering local servers, assign
it `provider-admin`, or a custom role (`POST /api/auth/roles`) that holds
`mcp_servers:local_launch` beside the permissions it already had.

An operator that registers remote servers (operator 0.17.26 and later) needs
three permissions: `mcp_servers:write` to register, `mcp_servers:lifecycle` to
start and deregister, and `policy:write` to deliver egress policy. From core
2.28.0 the built-in `kubernetes-operator` role holds those plus the two read
permissions; since 2.32.0 it also holds `mcp_servers:peer_identity`, which
registering a key-pinned server needs. Nothing else: no tool invocation, no
groups, no discovery approval, no config reload, no `mcp_servers:local_launch`.
Use it for the operator's key. `developer` has the
first two and the policy push gets `403`. Before 2.29.1 `provider-admin` had only the
last and registration got `403`; it now holds all three, plus tool invocation and
groups, which the operator never uses. Lifecycle is not scoped per server, so the role can
start servers it did not register.

`approval:resolve` is the permission that decides an approval. From 2.0.0 it is
enforced, so a caller without it receives `403` where it previously received
`200`; `approval:read` alone lists and reads approvals but cannot decide one.

### Assigning Roles

#### Static (in config.yaml)

```yaml
auth:
  role_assignments:
    - principal: "user:admin@company.com"
      role: admin
      scope: global

    - principal: "group:developers"
      role: developer
      scope: global

    # Tenant-scoped assignment
    - principal: "group:data-team"
      role: developer
      scope: "tenant:data-team"
```

*Since 2.34.2* the list is reconciled each time the server boots with
authentication on: a grant the file applied and no longer lists is revoked. It
matters only on a durable store (`sqlite`, `postgresql`, `event_sourcing`); the
`memory` store starts empty anyway. Before 2.34.2 a removed line's grant stayed
in force until it was revoked through the API.

- A grant made through `POST /api/auth/roles/assign` or by
  `mcp-hangar auth bootstrap-admin` is never revoked by a boot, even when the
  file lists the same role: the named actor takes the grant over from the file.
  `bootstrap-admin` applies the file's lines but revokes nothing.
- A grant written before 2.34.2 records no assigner, so a boot cannot tell a
  config line from an API call. One the file still lists is adopted by the file,
  and removing the line later revokes it. One the file does not list is kept and
  logged at every boot as `untracked_role_assignment_not_in_config`: revoke it
  with `DELETE /api/auth/roles/revoke`, or keep it by assigning it again through
  the API or listing it in the file.
- Every process that boots against the same durable store reconciles against
  its own file, so give every replica, and any other `serve` pointed at that
  store, the same `auth.role_assignments`.

#### Dynamic (via REST API)

```bash
curl -X POST http://localhost:8000/api/auth/roles/assign \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "user:john@company.com",
    "role_name": "developer",
    "scope": "global"
  }'
```

## Security Best Practices

### 1. Use HTTPS in Production

Always use HTTPS for MCP endpoints in production. Hangar refuses to start when
the URL it fetches signing keys from -- `jwks_uri`, or the issuer when no
`jwks_uri` is set -- is not `https://`; plain `http://` is accepted only for
`localhost`, `127.0.0.1` and `::1`. An issuer that is not `https://` while
`jwks_uri` is logs `oidc_issuer_not_https`.

### 2. Configure Trusted Proxies

If behind a load balancer, configure trusted proxies for correct client IP detection.
Hangar reads `X-Forwarded-For` only from a peer listed in `MCP_TRUSTED_PROXIES`,
a comma-separated list of addresses or CIDRs that defaults to `127.0.0.1,::1`:

```bash
export MCP_TRUSTED_PROXIES="10.0.0.0/8,172.16.0.0/12"
```

### 3. Rotate API Keys Regularly

Set expiration for API keys and rotate them periodically:

```bash
curl -X POST http://localhost:8000/api/auth/keys \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "principal_id": "service:ci",
    "name": "CI Pipeline Key",
    "expires_at": "2027-01-01T00:00:00+00:00"
  }'
```

`expires_at` is an ISO 8601 date-time. Since 2.34.2 one without a UTC offset is
read as UTC, and one that does not parse is refused with `422`. Before 2.34.2 a
value without an offset was accepted and every authentication with the key then
failed with a `500`.

### 4. Use Tenant Isolation

For multi-tenant deployments, use tenant-scoped roles:

```yaml
role_assignments:
  - principal: "group:team-alpha"
    role: developer
    scope: "tenant:alpha"
```

With more than one OIDC issuer, bind each to its tenants with `allowed_tenants`
(see [Binding each issuer to its tenants](#binding-each-issuer-to-its-tenants))
and give OIDC users and groups tenant-scoped roles only: a `global` grant to a
subject or group is shared by every trusted issuer.

### 5. Decide whether OPA may widen RBAC

With `auth.opa.enabled`, OPA is asked only when RBAC denies, and an OPA allow
overrides that deny with no tenant scope: a principal with no role, or one
confined to a tenant, is admitted to whatever the policy allows. Boot logs
`opa_may_widen_rbac` when this is the case. *Since 2.34.2*, to have OPA only
refuse more, set `require_both`:

```yaml
auth:
  opa:
    enabled: true
    require_both: true
```

With `require_both: true` RBAC is asked first, a principal RBAC refuses stays
refused, and OPA is asked only about what RBAC allows; an allow keeps the scope
RBAC granted at. OPA fails closed, so while it cannot be reached nothing is
allowed. The value must be a YAML boolean; anything else refuses the
configuration.

## Monitoring

Auth events are emitted as domain events and can be monitored:

- `AuthenticationSucceeded` - Successful authentication
- `AuthenticationFailed` - Failed authentication attempt
- `AuthorizationDenied` - Access denied
- `AuthorizationGranted` - Access granted

These are logged and can be sent to your observability stack.

## Troubleshooting

### "No valid credentials provided"

- Check that `auth.enabled: true` is set
- Verify the X-API-Key header is being sent (not `Authorization: Bearer`)

### "Invalid API key"

- Check for typos in the key
- A key without the `mcp_` prefix reads "Invalid API key format: must start with 'mcp_'"

### "API key has been revoked" / "API key has expired"

- The key was revoked, or passed its `expires_at`; mint a new one

### "Access denied"

- The principal doesn't have the required role. Registering a `subprocess`,
  `docker` or `container` server, or changing its `env`, also needs
  `mcp_servers:local_launch`, which `developer` does not hold
- Check role assignments via the REST API
  (`GET /api/auth/principals/roles?principal_id=<id>`; `GET /api/auth/roles`
  lists the built-in roles, not assignments)
- Verify the scope matches

## API Reference

### Configuration Schema

```yaml
auth:
  enabled: bool          # Master switch (default: false)
  allow_anonymous: bool  # Allow unauthenticated requests (default: false)

  api_key:
    enabled: bool        # Enable API key auth (default: true when auth enabled)
    header_name: str     # Header name (default: X-API-Key)

  oidc:
    enabled: bool        # Enable OIDC/JWT auth (default: false)
    issuer: str          # OIDC issuer URL
    audience: str        # Expected audience claim
    jwks_uri: str        # JWKS endpoint (auto-discovered if not set)
    resource_uri: str    # Public resource URI; also enforced as JWT aud when set
    subject_claim: str   # JWT claim for subject (default: sub)
    groups_claim: str    # JWT claim for groups (default: groups)
    tenant_claim: str    # JWT claim for tenant (default: tenant_id)
    issuers: []          # Multi-issuer trust entries; overrides top-level issuer
                         # each entry may set allowed_tenants: [str, ...]

  opa:
    enabled: bool        # Enable OPA policy engine (default: false)
    url: str             # OPA server URL (default: http://localhost:8181)
    policy_path: str     # Policy decision path (default: v1/data/mcp/authz/allow)
    timeout: float       # Request timeout in seconds (default: 5.0)
    require_both: bool   # RBAC and OPA must both allow (default: false)

  role_assignments: []   # Static role assignments, reconciled at boot
```
