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

  api_key:
    enabled: true
    header_name: X-API-Key
```

### 2. Create an API Key

The field names matter: the handler subscripts the body directly, so a wrong
name is a `500`, not a validation error.

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
      - issuer: https://issuer-b.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-b.example.com/jwks
        groups_claim: roles
```

When `resource_uri` is set, Hangar validates each token's `aud` claim against
that URI, regardless of the issuer entry's `audience`. This makes the value
advertised as RFC 9728 `resource` the same value enforced as the RFC 8707
resource indicator. Without `resource_uri`, each issuer uses its own configured
`audience`.

`auth.oidc.issuers` takes precedence over the legacy top-level `issuer` field.
Per-issuer entries inherit omitted claim mappings from top-level `oidc.*` fields.
Tokens with a missing, empty, non-string, or untrusted `iss` claim fail closed.

## Authorization (RBAC)

### Built-in Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `admin` | Full access | Everything |
| `provider-admin` | Manage servers, deliver egress policy, invoke tools | **`providers:read`**, **`policy:write`**, `provider:*`, `group:*`, `discovery:read/trigger/approve`, `tool:invoke`, `tool:list`, `metrics:read`, **`approval:read`**, **`approval:resolve`** |
| `developer` | Use tools, start servers on demand | `provider:read/list/start/load/load_verified/unload`, `providers:read/write/lifecycle`, `tool:invoke/list`, `group:read/list`, `discovery:read` |
| `viewer` | Read-only | `providers:read`, `provider:read/list`, `tool:list`, `metrics:read`, `group:read/list`, `discovery:read` |
| `auditor` | Audit logs and read-only oversight | `audit:read`, `metrics:read`, `provider:list`, `group:list`, `discovery:read`, **`approval:read`** |
| `service-account` | Default for service accounts — invoke tools | `provider:read/list`, `tool:invoke/list` |

Role names are exactly as shown. The name `mcp_server_admin` appeared in an
earlier revision of this table and does not exist — the role is
`provider-admin`, which kept its original name through the provider→MCP-server
rename.

The `provider:*` family is the pre-rename vocabulary and the REST API authorizes
against `mcp_servers:*` instead, so those entries currently grant nothing over
the API. That is why `provider-admin` gained `providers:read` and `policy:write`
in 2.2.0: without them it could not make a single call the Kubernetes operator
makes, and an operator key had to be `developer` or `admin`. **`provider-admin`
is now the least-privilege role for an operator API key** — it can read servers
and deliver compiled egress policy, and cannot create, delete or restart a
server through the API.

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

Always use HTTPS for MCP endpoints in production. The auth system will warn if OIDC issuer is not HTTPS.

### 2. Configure Trusted Proxies

If behind a load balancer, configure trusted proxies for correct client IP detection.
Trusted proxies are set programmatically via `FastMCPServerConfig`:

```python
from mcp_hangar.fastmcp_server.config import FastMCPServerConfig

config = FastMCPServerConfig(
    trusted_proxies=frozenset(["10.0.0.0/8", "172.16.0.0/12"]),
)
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

### 4. Use Tenant Isolation

For multi-tenant deployments, use tenant-scoped roles:

```yaml
role_assignments:
  - principal: "group:team-alpha"
    role: developer
    scope: "tenant:alpha"
```

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
- Verify the X-API-Key header is being sent
- Ensure the key has the correct prefix (`mcp_`)

### "Invalid API key"

- The key may have been revoked
- The key may have expired
- Check for typos in the key

### "Access denied"

- The principal doesn't have the required role
- Check role assignments via the REST API (`GET /api/auth/roles`)
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

  opa:
    enabled: bool        # Enable OPA policy engine (default: false)
    url: str             # OPA server URL
    policy_path: str     # Policy decision path

  role_assignments: []   # Static role assignments
```
