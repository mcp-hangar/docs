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

3. Mint the first key. Not over HTTP: `/api/auth/**` requires an admin
   principal with no carve-out for the first call, so an unauthenticated
   `POST /api/auth/keys` answers `401`. Stop the gateway and run:

   ```bash
   mcp-hangar auth bootstrap-admin --config config.yaml \
     --principal service:my-app --show-key
   ```

   ```
   Initial global admin bootstrapped.
     principal : service:my-app
     key id    : N3xQ...
     api key   : mcp_QWBXSRQ4OW...

   This secret is shown once and is not recoverable. It is stored hashed.
   Anyone holding it is a global administrator of this deployment.
   ```

   > **`--show-key` matters and the claim is one-shot.** Without the flag the
   > command prints no secret -- right when the principal is an OIDC subject
   > that authenticates on its own identity, and useless when API keys are all
   > you have. On this recipe's configuration, which has no `auth.oidc` block,
   > omitting it is therefore **refused before the claim is spent**:
   >
   > ```
   > Error: Nothing could use this administrator: API keys are the only
   > authenticator, and the key's secret would not be printed.
   > ```
   >
   > So a forgotten flag costs you one command. What it used to cost is the
   > deployment: the claim was spent, and a second run exits 1 with "the initial
   > administrator has already been bootstrapped" while the secret sits in the
   > database as a hash.
   >
   > *Before 2.5.0 the secret was discarded unconditionally and this recipe's
   > configuration had no way to reach its own gateway.*

   Start the gateway again. With that key in hand, later keys are ordinary API
   calls:

   ```bash
   curl -X POST http://localhost:8000/api/auth/keys \
     -H "X-API-Key: <the key from bootstrap>" \
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
| ------ | -------- |
| `admin` | Everything |
| `provider-admin` | Manage servers and groups, deliver compiled egress policy (`policy:write`). The least-privilege role for a Kubernetes operator API key. |
| `developer` | Invoke tools, read and manage server state. Cannot touch egress policy. |
| `viewer` | Read-only access |

Tool access policies add fine-grained control per (principal, MCP server, tool) tuple.

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `auth.enabled` | bool | `false` | Enable authentication |
| `auth.allow_anonymous` | bool | `false` | Allow unauthenticated requests |
| `auth.api_key.enabled` | bool | `true` | Enable API key authentication |
| `auth.api_key.header_name` | string | `X-API-Key` | HTTP header for API key |

## What's Next

You've secured access. Before going to production, run through the full checklist.

--> [13 -- Production Checklist](13-production-checklist.md)
