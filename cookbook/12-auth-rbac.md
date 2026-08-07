# 12 -- Auth & RBAC

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar in HTTP mode
> **Time:** 10 minutes
> **Adds:** API key authentication and role-based access control

## The Problem

Your Hangar instance is accessible to everyone on the network. You need to control who can invoke tools, start MCP servers, or manage configuration. Different teams need different access levels.

## The Config

```yaml
# config.yaml -- Recipe 12: Auth & RBAC
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: "http://localhost:8080/mcp"
    health_check_interval_s: 10

auth:                                    # NEW: authentication config
  enabled: true                          # NEW: enable auth
  allow_anonymous: false                 # NEW: require auth for all requests

  api_key:                               # NEW: API key config
    enabled: true                        # NEW: enable API key auth
    header_name: X-API-Key               # NEW: header to read key from

  storage:                               # NEW: durable, and required below
    driver: sqlite                       # the default is `memory`
    path: data/auth.db
```

The `storage` block is not optional here. Every `/api/auth/**` route requires an
admin principal, so there is no unauthenticated call that mints the first key --
`POST /api/auth/keys` on a fresh gateway answers `401`. The way out is the CLI,
and it refuses the default `memory` driver, because a key minted into memory is
gone the moment the process it was minted in exits.

## Try It

1. Start Hangar:

   ```bash
   mcp-hangar serve --http --host 127.0.0.1 --port 8000
   ```

2. Try an unauthenticated request -- it fails:

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/mcp_servers
   ```

   ```
   401
   ```

3. Grant the first administrator. Not over HTTP: `/api/auth/**` requires an
   admin principal with no carve-out for the first call, so an unauthenticated
   `POST /api/auth/keys` answers `401`. Stop the gateway and run:

   ```bash
   mcp-hangar auth bootstrap-admin --config config.yaml --principal user:admin
   ```

   > **Read this before you plan around it.** The command assigns the global
   > `admin` role to a principal that **already has a way to authenticate** --
   > an OIDC subject, for instance. It creates an API key row as part of the
   > same atomic claim but **deliberately does not print the secret**, so it
   > cannot hand you a usable key for an API-key-only deployment. It is
   > also one-shot: a second run exits 1 with "the initial administrator has
   > already been bootstrapped".
   >
   > So on this recipe's configuration -- API keys and nothing else -- there is
   > no supported way to obtain the first usable credential. To administer a
   > gateway over HTTP today, give the admin an identity provider
   > ([recipe 22](22-external-multitenant-oidc.md)) and bootstrap that
   > principal; API keys are then minted by that admin for everything else.

   With an admin credential in hand, later keys are ordinary API calls:

   ```bash
   curl -X POST http://localhost:8000/api/auth/keys \
     -H "Authorization: Bearer <admin_token>" \
     -H "Content-Type: application/json" \
     -d '{"principal_id": "service:my-app", "name": "My App Key"}'
   ```

   ```json
   {"key_id": "...", "raw_key": "mcp_aBcDeFg...", "principal_id": "service:my-app", "name": "My App Key"}
   ```

   Save the `raw_key` -- it is shown only once.

4. Use the key:

   ```bash
   curl -H "X-API-Key: mcp_aBcDeFg..." http://localhost:8000/api/mcp_servers
   ```

   ```json
   {"mcp_servers": [...]}
   ```

5. Assign a role:

   ```bash
   curl -X POST http://localhost:8000/api/auth/roles/assign \
     -H "X-API-Key: mcp_admin_key..." \
     -H "Content-Type: application/json" \
     -d '{"principal_id": "service:my-app", "role_name": "developer"}'
   ```

6. Set a tool access policy:

   ```bash
   curl -X POST http://localhost:8000/api/auth/policies/provider/my-mcp \
     -H "X-API-Key: mcp_admin_key..." \
     -H "Content-Type: application/json" \
     -d '{"allow_list": ["service:my-app"], "deny_list": []}'
   ```

## What Just Happened

Enabling auth adds the `AuthMiddleware` to the HTTP stack. Every request must include a valid API key in the `X-API-Key` header. The key is hashed and looked up in the auth store. The principal's roles determine what operations are allowed.

Built-in roles:

| Role | Can do |
|------|--------|
| `admin` | Everything |
| `provider-admin` | Manage servers and groups, deliver compiled egress policy (`policy:write`). The least-privilege role for a Kubernetes operator API key. |
| `developer` | Invoke tools, read and manage server state. Cannot touch egress policy. |
| `viewer` | Read-only access |

Tool access policies add fine-grained control per (principal, MCP server, tool) tuple.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auth.enabled` | bool | `false` | Enable authentication |
| `auth.allow_anonymous` | bool | `false` | Allow unauthenticated requests |
| `auth.api_key.enabled` | bool | `true` | Enable API key authentication |
| `auth.api_key.header_name` | string | `X-API-Key` | HTTP header for API key |

## What's Next

You've secured access. Before going to production, run through the full checklist.

--> [13 -- Production Checklist](13-production-checklist.md)
