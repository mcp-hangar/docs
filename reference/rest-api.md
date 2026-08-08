# REST API Reference

Complete reference for all REST API endpoints exposed by MCP Hangar in HTTP mode.

**Base URL:** `http://localhost:8000/api`

All endpoint paths shown below are relative to this base URL. Every route resolves only under the `/api` prefix (e.g. `GET /mcp_servers` is served at `GET /api/mcp_servers`).

**Collection endpoints carry a trailing slash.** `GET /api/mcp_servers` answers
`307` and redirects to `/api/mcp_servers/`; `curl` does not follow a redirect
unless you pass `-L`, and a `POST` that follows one without `--post301` loses
its body. The same applies to `/api/groups/`, `/api/tools/`, `/api/config/` and
`/api/system/`.

All responses are JSON. Errors are **nested**:

```json
{"error": {"code": "<ExceptionType>", "message": "<description>", "details": {"field": "..."} }}
```

`details` is `null` unless the error carries structured context. The HTTP
status is in the status line, not the body.

Authentication failures are the one exception -- they are produced by the
middleware before the handler chain and use a flat shape:

```json
{"error": "authentication_failed", "message": "No valid credentials provided", "details": {}}
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
| `source` | string | No | `"api"` | Provenance recorded on the registration |

`volumes`, `network` and `read_only` are **not** read by this route. They are
accepted by the request parser and dropped: the command it builds carries only
the fields above, so a container registered here gets the container defaults
rather than the ones you sent. Declare those in `config.yaml`, where they are
honoured.

A private or link-local `endpoint` is refused with `400 {"error":
"ssrf_blocked"}`. That check applies to human-supplied endpoints only --
discovery supplies a pod IP with its provenance attached and is accepted.

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
| `graceful` | bool | `true` | Graceful reload |

Sending `config_path` is **refused** with `422` and
`config_path is not accepted; reload always targets the server's own
configuration file`. Reload re-reads the file the process was started with;
there is no way to point it at another one over HTTP.

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
{"path": "/path/to/config.yaml.bak1"}
```

The backup is written **next to the configuration file** as `<config>.bak1`,
rotating older ones to `.bak2` and beyond. That directory has to be writable by
the process, and in the published container image it is not: `/app` is owned by
root and the gateway runs as `hangar`.

*Since 2.5.0* that answers **503** with the reason --
`could not write the backup beside 'config.yaml': Permission denied` -- rather
than a bare `500` and `An internal server error occurred.`. Mount a writable
directory and point `--config` at it if you need this endpoint.

```json
```

### Config Diff

```
GET /config/diff
```

Compares on-disk configuration with current in-memory state.

**Response 200:**

```json
{"has_diff": true, "diff": "--- on-disk\n+++ in-memory\n@@ ...", "on_disk": {...}, "in_memory": {...}}
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
    "total_invocations": 42,
    "total_failures": 1,
    "overall_success_rate": 0.976,
    "uptime_seconds": 3600.5,
    "version": "2.5.0",
    "instance": {
      "instance_id": "hangar-7f9c4d2b1a-a3f19c",
      "coordinates_with_peers": false,
      "manages_fleet": true,
      "storage_is_shareable": false,
      "rate_limits_are_per_instance": true
    }
  }
}

The counter is `total_invocations`, not `total_tool_calls`. `instance` is
present from 2.5.0 and describes the replica that answered -- see
[Running more than one replica](../cookbook/25-multiple-replicas.md).
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

## L7 Egress Policy

Attach, replace, or clear the L7 egress policy (compiled `MCPEgressPolicy`) on a
single MCP server. The core policy engine and this REST intake are available in
v1.6.0; end-to-end delivery from a Kubernetes `MCPEgressPolicy` custom resource
depends on the operator's controller compiling and pushing the policy (shipping
in a later operator release). L7 egress is the **last** gate on the invocation
path, evaluated inside `invoke_tool` immediately before the upstream call.

### Set L7 Policy

```
POST /mcp_servers/{mcp_server_id}/l7_policy
PUT  /mcp_servers/{mcp_server_id}/l7_policy
```

Attaches or replaces the compiled L7 policy on an MCP server. `POST` and `PUT`
behave identically. Requires `mcp_servers:write`.

**Request body:** the compiled policy the operator derives from an
`MCPEgressPolicy`:

| Field | Type | Description |
|-------|------|-------------|
| `tools` | dict | Tool-name globs: `allow`, `deny`, `requireApproval` |
| `arguments` | dict | Argument-level constraints: `secretPatterns`, `maxPayloadBytes` |
| `defaultAction` | string | Action when no rule matches |

> **`requireApproval` fails closed.** A synchronous `requireApproval` match
> **blocks** the call — it is not an interactive prompt-and-wait approval queue.
> That queue is a different control: the tool-access
> [`approval_list`](configuration.md#holding-a-tool-for-a-human-approval_list),
> which holds the call for a human decision. The two are configured separately
> and an egress `requireApproval` match does not enqueue an approval.

**Response 200:**

```json
{"mcp_server_id": "math", "l7_policy_set": true}
```

**Response 400:** `{"error": "invalid_l7_policy", "detail": "..."}` when the body
is not a valid compiled policy.

**Response 404:** MCP Server not found.

### Clear L7 Policy

```
DELETE /mcp_servers/{mcp_server_id}/l7_policy
```

Clears the L7 policy on an MCP server, disabling L7 enforcement for it. Requires
`mcp_servers:write`.

**Response 200:**

```json
{"mcp_server_id": "math", "l7_policy_set": false}
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

## Approvals

Available when the approval service is enabled. Paths below are the 2.x routes, served under the `/api` mount — verified against core's published route inventory (`api-routes.json`). On the closed 1.6.x line these lived under `/enterprise/approvals`.

These routes became usable in **2.1.0**. Before that they read an application-state field that nothing ever populated, so `GET /api/approvals` answered `500` with an `AttributeError` on every deployment ([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678)). The service is now published onto application state from a single place shared by the HTTP-serve path, the server factory and any test client, and the routes fall back to the application context — the same object the enforcement path reads — so the API and enforcement cannot hold different services. When there is genuinely no gate service, these routes answer **503**, not a stack trace.

Something has to put a tool behind the gate before anything appears here: see [`approval_list`](configuration.md#holding-a-tool-for-a-human-approval_list).

### List Approvals

```
GET /api/approvals?state={state}&provider_id={id}
```

| Parameter | In | Type | Default | Description |
|-----------|------|------|---------|-------------|
| `state` | query | string | `pending` | Filter: `pending`, `approved`, `denied`, `expired` |
| `provider_id` | query | string | -- | Optional provider filter |

**Response 200:** JSON array of approval request objects.

### Get Approval

```
GET /api/approvals/{approval_id}
```

**Response 200:** Approval request object.

**Response 404:** Approval not found.

### Resolve Approval

```
POST /api/approvals/{approval_id}/resolve
```

Approves or denies a pending approval. Requires an authenticated principal holding `approval:resolve`; the decision is attributed to that principal.

From 2.0.0 this is the **only** way in. The Slack HMAC callback branch was removed, and the client-supplied `x-principal-id` header no longer sets identity. A Slack integration now runs as a delivery adapter that verifies the vendor signature itself and calls this endpoint with an ordinary token — see [Approval delivery adapters](../guides/APPROVAL_ADAPTERS.md).

On a gateway with auth disabled the decision is attributed to the system principal rather than refused: refusing there would decide nothing.

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
