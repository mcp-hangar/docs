# REST API Reference

Complete reference for all REST API endpoints exposed by MCP Hangar in HTTP mode.

**Base URL:** `http://localhost:8000/api`

All endpoint paths shown below are relative to this base URL. Every route resolves only under the `/api` prefix (e.g. `GET /mcp_servers` is served at `GET /api/mcp_servers`).

All responses are JSON. Error responses return:

```json
{"error": "<ExceptionType>", "message": "<description>", "status_code": <code>}
```

---

## MCP servers

### List MCP servers

```
GET /mcp_servers?state={state}
```

| Parameter | In | Type | Required | Description |
|-----------|------|------|----------|-------------|
| `state` | query | string | No | Filter: `cold`, `ready`, `degraded`, `dead` |

**Response 200:**

```json
{
  "mcp_servers": [
    {
      "mcp_server": "math",
      "state": "ready",
      "mode": "subprocess",
      "alive": true,
      "tools_count": 5,
      "health_status": "healthy",
      "tools_predefined": false,
      "description": "Math computation mcp_server"
    }
  ]
}
```

### Create MCP Server

```
POST /mcp_servers
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mcp_server_id` | string | Yes | -- | Unique identifier |
| `mode` | string | Yes | -- | `subprocess`, `docker`, or `remote` |
| `command` | list[string] | For subprocess | -- | Command to run |
| `image` | string | For docker | -- | Docker image |
| `endpoint` | string | For remote | -- | HTTP endpoint URL |
| `env` | dict | No | `{}` | Environment variables |
| `idle_ttl_s` | int | No | `300` | Idle timeout in seconds |
| `health_check_interval_s` | int | No | `60` | Health check interval |
| `description` | string | No | -- | Human-readable description |
| `volumes` | list[string] | No | `[]` | Docker volume mounts |
| `network` | string | No | `"none"` | Docker network mode |
| `read_only` | bool | No | `true` | Read-only filesystem (docker) |

**Response 201:**

```json
{"mcp_server_id": "math", "created": true}
```

### Get MCP Server

```
GET /mcp_servers/{mcp_server_id}
```

**Response 200:** MCP Server detail object with tools, health, and configuration.

**Response 404:** MCP Server not found.

### Update MCP Server

```
PUT /mcp_servers/{mcp_server_id}
PATCH /mcp_servers/{mcp_server_id}
```

Both `PUT` and `PATCH` are accepted and behave identically (partial update).

**Request body (all fields optional):**

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | New description |
| `env` | dict | New environment variables (replaces existing) |
| `idle_ttl_s` | int | New idle timeout |
| `health_check_interval_s` | int | New health check interval |

**Response 200:**

```json
{"mcp_server_id": "math", "updated": true}
```

### Delete MCP Server

```
DELETE /mcp_servers/{mcp_server_id}
```

Stops the MCP server if running, then removes it from the registry.

**Response 200:**

```json
{"mcp_server_id": "math", "deleted": true}
```

### Start MCP Server

```
POST /mcp_servers/{mcp_server_id}/start
```

**Response 200:** Start result object.

### Stop MCP Server

```
POST /mcp_servers/{mcp_server_id}/stop
```

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reason` | string | `"user_request"` | Reason for stopping |

**Response 200:** Stop result object.

### Block MCP Server

```
POST /mcp_servers/{mcp_server_id}/block
```

Permanently blocks an MCP server for detection enforcement (stops it with reason `detection_enforcement:block`).

**Response 200:**

```json
{"mcp_server_id": "math", "blocked": true}
```

### Get MCP Server Tools

```
GET /mcp_servers/{mcp_server_id}/tools
```

**Response 200:**

```json
{
  "tools": [
    {"name": "add", "description": "Add two numbers", "parameters": {...}}
  ]
}
```

### Get MCP Server Health

```
GET /mcp_servers/{mcp_server_id}/health
```

**Response 200:** Health status object with check history.

### Get MCP Server Logs

```
GET /mcp_servers/{mcp_server_id}/logs?lines={n}
```

| Parameter | In | Type | Default | Range | Description |
|-----------|------|------|---------|-------|-------------|
| `lines` | query | int | `100` | 1--1000 | Number of recent lines |

**Response 200:**

```json
{
  "logs": [
    {"timestamp": "2026-03-23T10:15:30", "line": "...", "mcp_server_id": "math", "stream": "stderr"}
  ],
  "mcp_server_id": "math",
  "count": 42
}
```

### Get Tool Invocation History

```
GET /mcp_servers/{mcp_server_id}/tools/history?limit={n}&from_position={pos}
```

| Parameter | In | Type | Default | Range | Description |
|-----------|------|------|---------|-------|-------------|
| `limit` | query | int | `100` | 1--500 | Max records |
| `from_position` | query | int | `0` | -- | Event store version offset |

**Response 200:**

```json
{
  "mcp_server_id": "math",
  "history": [...],
  "total": 42
}
```

---

## Groups

### List Groups

```
GET /groups
```

**Response 200:**

```json
{
  "groups": [
    {
      "group_id": "llm-pool",
      "state": "healthy",
      "strategy": "round_robin",
      "members": [...],
      "circuit_breaker_state": "closed"
    }
  ]
}
```

### Create Group

```
POST /groups
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `group_id` | string | Yes | -- | Unique identifier |
| `strategy` | string | No | `"round_robin"` | Load balancing strategy |
| `min_healthy` | int | No | `1` | Minimum healthy members |
| `description` | string | No | -- | Description |

**Response 201:**

```json
{"group_id": "llm-pool", "created": true}
```

### Get Group

```
GET /groups/{group_id}
```

**Response 200:** Group detail with members and circuit breaker state.

### Update Group

```
PUT /groups/{group_id}
```

**Request body (all optional):**

| Field | Type | Description |
|-------|------|-------------|
| `strategy` | string | New strategy |
| `min_healthy` | int | New minimum healthy count |
| `description` | string | New description |

**Response 200:**

```json
{"group_id": "llm-pool", "updated": true}
```

### Delete Group

```
DELETE /groups/{group_id}
```

**Response 200:**

```json
{"group_id": "llm-pool", "deleted": true}
```

### Rebalance Group

```
POST /groups/{group_id}/rebalance
```

Re-checks member health and resets circuit breaker if applicable.

**Response 200:**

```json
{"status": "rebalanced", "group_id": "llm-pool"}
```

### Add Group Member

```
POST /groups/{group_id}/members
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `member_id` | string | Yes | -- | MCP Server ID to add |
| `weight` | int | No | `1` | Routing weight |
| `priority` | int | No | `1` | Routing priority |

**Response 201:**

```json
{"group_id": "llm-pool", "mcp_server_id": "llm-1", "added": true}
```

### Remove Group Member

```
DELETE /groups/{group_id}/members/{member_id}
```

**Response 200:**

```json
{"group_id": "llm-pool", "mcp_server_id": "llm-1", "removed": true}
```

---

## Discovery

### List Sources

```
GET /discovery/sources
```

**Response 200:**

```json
{"sources": [{"source_id": "...", "type": "docker", "mode": "additive", "enabled": true, "last_scan": "..."}]}
```

### Register Source

```
POST /discovery/sources
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source_type` | string | Yes | -- | `docker`, `filesystem`, `kubernetes`, `entrypoint` |
| `mode` | string | Yes | -- | `additive` or `authoritative` |
| `enabled` | bool | No | `true` | Activate immediately |
| `config` | dict | No | `{}` | Source-specific configuration |

**Response 201:**

```json
{"source_id": "...", "registered": true}
```

### Update Source

```
PUT /discovery/sources/{source_id}
```

**Request body (all optional):** `mode`, `enabled`, `config`.

**Response 200:**

```json
{"source_id": "...", "updated": true}
```

### Delete Source

```
DELETE /discovery/sources/{source_id}
```

**Response 200:**

```json
{"source_id": "...", "deregistered": true}
```

### Trigger Scan

```
POST /discovery/sources/{source_id}/scan
```

**Response 200:**

```json
{"source_id": "...", "scan_triggered": true, "mcp_servers_found": 3}
```

### Enable/Disable Source

```
PUT /discovery/sources/{source_id}/enable
```

**Request body:**

```json
{"enabled": true}
```

**Response 200:**

```json
{"source_id": "...", "enabled": true}
```

### List Pending MCP servers

```
GET /discovery/pending
```

**Response 200:**

```json
{"pending": [{"name": "new-mcp-server", "source": "docker", "mode": "remote", ...}]}
```

### List Quarantined MCP servers

```
GET /discovery/quarantined
```

**Response 200:**

```json
{"quarantined": {...}}
```

### Approve MCP Server

```
POST /discovery/approve/{name}
```

**Response 200:** Approval result.

### Reject MCP Server

```
POST /discovery/reject/{name}
```

**Response 200:** Rejection result.

---

## Configuration

### Get Config

```
GET /config
```

Returns the current server configuration with sensitive fields stripped.

**Response 200:**

```json
{"config": {"mcp_servers": [...]}}
```

### Reload Config

```
POST /config/reload
```

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `config_path` | string | server default | Path to config file |
| `graceful` | bool | `true` | Graceful reload |

**Response 200:**

```json
{"status": "reloaded", "result": {...}}
```

### Export Config

```
POST /config/export
```

Serializes current in-memory state to YAML.

**Response 200:**

```json
{"yaml": "mcp_servers:\n  math:\n    mode: subprocess\n    ..."}
```

### Backup Config

```
POST /config/backup
```

Creates a rotating backup of the current configuration.

**Response 200:**

```json
{"backup_path": "/path/to/backup.yaml", "created": true}
```

### Config Diff

```
GET /config/diff
```

Compares on-disk configuration with current in-memory state.

**Response 200:**

```json
{"diff": "--- on-disk\n+++ in-memory\n@@ ...", "has_changes": true}
```

---

## System

### Get System Info

```
GET /system
```

**Response 200:**

```json
{
  "system": {
    "total_mcp_servers": 5,
    "mcp_servers_by_state": {"ready": 3, "cold": 2},
    "total_tools": 15,
    "total_tool_calls": 42,
    "uptime_seconds": 3600.5,
    "version": "1.3.0"
  }
}
```

### Get Current User

```
GET /system/me
```

Returns the current authentication status. Used by the SPA to check whether a user is logged in. When auth is not enabled, returns `authenticated: false`.

**Response 200:**

```json
{"authenticated": true, "principal": {"id": "...", "type": "user"}}
```

---

## Tools

### List All Tools

```
GET /tools
```

Lists all tools across all MCP servers (used by the supervisor to sync tool inventory).

**Response 200:**

```json
{
  "tools": [
    {"mcp_server_id": "math", "tool_name": "add", "description": "Add two numbers", "input_schema": "..."}
  ]
}
```

---

## Sessions

### Suspend Session

```
POST /sessions/{session_id}/suspend
```

Adds a session to the in-memory suspended registry.

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reason` | string | -- | Reason for suspension |

**Response 200:**

```json
{"session_id": "...", "suspended": true}
```

### Unsuspend Session

```
DELETE /sessions/{session_id}/suspend
```

Removes a session from the suspended registry.

**Response 200:**

```json
{"session_id": "...", "suspended": false}
```

---

## Auth Management

### Create API Key

```
POST /auth/keys
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `principal_id` | string | Yes | -- | Principal this key authenticates as |
| `name` | string | Yes | -- | Human-readable key name |
| `created_by` | string | No | `"system"` | Creator principal |
| `expires_at` | string | No | -- | ISO8601 expiry datetime |

**Response 201:**

```json
{"key_id": "...", "raw_key": "mcp_...", "principal_id": "...", "name": "..."}
```

!!! warning
    The `raw_key` is returned only once. Store it securely.

### Revoke API Key

```
DELETE /auth/keys/{key_id}
```

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `revoked_by` | string | `"system"` | Revoking principal |
| `reason` | string | `""` | Revocation reason |

### List API Keys

```
GET /auth/keys
```

| Parameter | In | Type | Required | Description |
|-----------|------|------|----------|-------------|
| `principal_id` | query | string | Yes | Principal whose keys to list |
| `include_revoked` | query | bool | No | Include revoked keys (default `true`) |

### List All Roles

```
GET /auth/roles/all
```

| Parameter | In | Type | Required | Description |
|-----------|------|------|----------|-------------|
| `include_builtin` | query | bool | No | Include built-in roles (default `true`) |

### List Built-in Roles

```
GET /auth/roles
```

### Get Role

```
GET /auth/roles/{role_name}
```

### Create Custom Role

```
POST /auth/roles
```

### Update Custom Role

```
PATCH /auth/roles/{role_name}
```

### Delete Custom Role

```
DELETE /auth/roles/{role_name}
```

### Assign Role

```
POST /auth/roles/assign
```

**Request body:**

```json
{"principal_id": "...", "role_name": "developer", "scope": "global", "assigned_by": "system"}
```

### Revoke Role

```
DELETE /auth/roles/revoke
```

**Request body:**

```json
{"principal_id": "...", "role_name": "developer", "scope": "global", "revoked_by": "system"}
```

### List Principals

```
GET /auth/principals
```

### List Roles for Principal

```
GET /auth/principals/roles
```

| Parameter | In | Type | Required | Description |
|-----------|------|------|----------|-------------|
| `principal_id` | query | string | Yes | Principal whose roles to list |
| `scope` | query | string | No | Scope filter (default `*` = all) |

### List Permissions

```
GET /auth/permissions
```

Lists all known permission resource types and their available actions.

**Response 200:**

```json
{"permissions": [{"resource_type": "mcp_servers", "actions": ["read", "write", "..."]}]}
```

### Check Permission

```
POST /auth/check-permission
```

**Request body:**

```json
{"principal_id": "...", "permission": "mcp_servers:start"}
```

### Get Tool Access Policy

```
GET /auth/policies/{scope}/{target_id}
```

| Parameter | In | Type | Required | Description |
|-----------|------|------|----------|-------------|
| `scope` | path | string | Yes | `provider`, `group`, or `member` |
| `target_id` | path | string | Yes | Identifier of the provider, group, or member |

### Set Tool Access Policy

```
POST /auth/policies/{scope}/{target_id}
```

**Request body:**

```json
{"allow_list": ["tool_a", "tool_b*"], "deny_list": ["tool_c"]}
```

### Clear Tool Access Policy

```
DELETE /auth/policies/{scope}/{target_id}
```

---

## Agent Policy

### Push Agent Policy

```
POST /agent/policy
```

Applies a batch of tool access policies (allow/deny/require-approval/audit) per MCP server. Use `mcp_server_id: "*"` for a global policy.

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tool_policies` | list[dict] | `[]` | Policy entries (`mcp_server_id`, `action`, `tool_name`, `approval_timeout_seconds`) |
| `version` | int | `0` | Policy version |

**Response 200:**

```json
{"status": "ok", "version": 3, "applied": 2}
```

---

## Admin Tools

Runtime tool withdrawal/restore. Requires admin (`mcp_servers` resource, `lifecycle` action).

### Withdraw Tool

```
POST /admin/tools/{server}/{tool}/withdraw
```

Withdraws a tool at runtime (survives reload). Withdrawal persists in the runtime overlay.

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tenant_id` | string | `null` | Tenant to withdraw for. Omit/null withdraws globally for all tenants. |

**Response 200:**

```json
{"withdrawn": true, "mcp_server": "math", "tool": "add", "tenant_id": null}
```

### Restore Tool

```
POST /admin/tools/{server}/{tool}/restore
```

Removes a runtime withdrawal (config-declared withdrawals persist independently).

**Request body (optional):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tenant_id` | string | `null` | Tenant to restore. Omit/null removes the entire runtime entry. |

**Response 200:**

```json
{"restored": true, "mcp_server": "math", "tool": "add", "tenant_id": null}
```

---

## Enterprise Approvals

Available when the enterprise approval service is enabled.

### List Approvals

```
GET /enterprise/approvals?state={state}&provider_id={id}
```

| Parameter | In | Type | Default | Description |
|-----------|------|------|---------|-------------|
| `state` | query | string | `pending` | Filter: `pending`, `approved`, `denied`, `expired` |
| `provider_id` | query | string | -- | Optional provider filter |

**Response 200:** JSON array of approval request objects.

### Get Approval

```
GET /enterprise/approvals/{approval_id}
```

**Response 200:** Approval request object.

**Response 404:** Approval not found.

### Resolve Approval

```
POST /enterprise/approvals/{approval_id}/resolve
```

Approves or denies a pending approval. Accepts JWT auth (with `approval:resolve` permission) or a Slack HMAC callback.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision` | string | Yes | `approve` or `deny` |
| `reason` | string | No | Optional resolution reason |

**Response 200:** Resolution result.

---

## WebSocket Endpoints

### Events Stream

```
ws://host:port/api/ws/events
```

Streams all domain events as JSON frames.

See the [WebSockets guide](../guides/WEBSOCKETS.md) for connection details.
