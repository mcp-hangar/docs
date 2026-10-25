# REST API Reference

Complete reference for all REST API endpoints exposed by MCP Hangar in HTTP mode.
This page is the authoritative reference; the [REST API guide](../guides/REST_API.md)
is an overview that links here.

**Base URL:** `http://localhost:8000/api`

All endpoint paths shown below are relative to this base URL. Every route resolves only under the `/api` prefix (e.g. `GET /mcp_servers` is served at `GET /api/mcp_servers`).

**Collection endpoints carry a trailing slash.** `GET /api/mcp_servers` answers
`307` and redirects to `/api/mcp_servers/`; `curl` does not follow a redirect
unless you pass `-L` (a `307` keeps the method and body, so a `POST` followed
with `-L` arrives intact). Using the trailing slash avoids the round trip. The
same applies to `/api/groups/`, `/api/tools/`, `/api/config/` and
`/api/system/`.

Responses are JSON, with one exception: a path or method the API does not
serve is answered by the web framework as plain text (`404 Not Found`,
`405 Method Not Allowed`) when authentication is off. With authentication on,
an authenticated request to such a path or method matches no entry in the
route table and is refused first, with `403` `AccessDeniedError` and the
reason `route has no permission mapping`. Domain errors are **nested**:

```json
{"error": {"code": "<ExceptionType>", "message": "<description>", "details": {"field": "..."} }}
```

`details` is `null` unless the error carries structured context. The HTTP
status is in the status line, not the body. The status follows the exception:
`McpServerNotFoundError` and `ToolNotFoundError` are `404`, `ValidationError`
`422`, `AuthenticationError` `401`, `AccessDeniedError` and `AuthorizationError`
`403`, `RateLimitExceeded` `429` (with `Retry-After` when the refill time is
known), `McpServerNotReadyError` and `McpServerNotHereError` `409`,
`McpServerDegradedError` `503`, `ToolTimeoutError` `504`, and any other error
`500` with the generic message `An internal server error occurred.`.

Two other shapes are flat. Authentication failures are produced by the
middleware before the handler chain:

```json
{"error": "authentication_failed", "message": "No valid credentials provided", "details": {"auth_method": "none", "expected_methods": ["ApiKeyAuthenticator"]}}
```

Request-body checks made inside a handler answer `400` with a flat code, e.g.
`{"error": "missing_fields", "detail": "required field(s) absent: group_id"}`,
`{"error": "invalid_body", ...}` or `{"error": "invalid_mode", ...}`. *Since
2.34.2* a body that is not JSON at all, or is JSON but not an object, answers
`400 invalid_body` on the routes that need one: server create and update,
groups, discovery sources, L7 policy, auth and approval resolution. Before, a
body that did not parse was a `500` there. Routes whose body is optional (stop,
config reload and backup, admin tools, key revocation) ignore one that does not
parse. The approvals routes use a flat `{"error": "<message>"}` throughout.

## Required permissions

With authentication enabled, every route is authorized from one route table;
a route missing from it is denied. A refusal is `403` with `AccessDeniedError`.

| Route | Permission |
| ------- | ------------ |
| `GET /mcp_servers`, `/mcp_servers/{id}` and its `tools`, `tools/history`, `health`, `logs` | `mcp_servers:read` |
| `POST /mcp_servers`, `PUT`/`PATCH /mcp_servers/{id}` | `mcp_servers:write`; also `mcp_servers:local_launch` to register a server that is not `remote`, or to set `env` on one (2.34.2+); also `mcp_servers:peer_identity` for a `tls.peer_identity` |
| `DELETE /mcp_servers/{id}` | `mcp_servers:write` and `mcp_servers:lifecycle`; also `mcp_servers:peer_identity` for a key-pinned server |
| `DELETE /mcp_servers/{id}/peer_identity` | `mcp_servers:peer_identity` |
| `POST /mcp_servers/{id}/start`, `/stop`, `/block`; `/sessions/{id}/suspend`; `/admin/tools/.../withdraw`, `/restore` | `mcp_servers:lifecycle`; a withdraw or restore for every tenant (no `tenant_id`) also needs `admin` (`*:*`) |
| `GET /admin/tools/pins` | `audit:read` |
| `GET /mcp_servers/{id}/l7_policy` | `policy:read` |
| `POST`/`PUT`/`DELETE /mcp_servers/{id}/l7_policy` | `policy:write` |
| `GET /groups`, `/groups/{id}` | `group:read` |
| `POST /groups` | `group:create` |
| `PUT /groups/{id}`, `/rebalance`, members add/remove | `group:update` |
| `DELETE /groups/{id}` | `group:delete` |
| `GET /discovery/sources`, `/pending`, `/quarantined` | `discovery:read` |
| `POST /discovery/sources/{id}/scan` | `discovery:trigger` |
| Other source management, `/discovery/approve`, `/discovery/reject` | `discovery:approve` |
| `GET /config`, `GET /config/diff`, `POST /config/export` | `config:read` |
| `POST /config/backup` | `config:update` |
| `POST /config/reload` | `config:reload` |
| `GET /tools` | `tool:list` |
| `GET /system`, `/system/me` | any authenticated principal |
| `GET /approvals`, `/approvals/{id}` | `approval:read` |
| `POST /approvals/{id}/resolve` | `approval:resolve` |
| `/ws/events` | `audit:read` |
| everything under `/auth` | `admin` (only `*:*` satisfies it) |

A grant held only at tenant scope passes just the tenant-aware routes --
`tools/history`, `/admin/tools/...`, `/approvals/...` and `/ws/events` -- and
each of those confines what it reads or changes to that tenant. Every other
route needs a global grant. With authentication disabled none of this applies.

---

## MCP servers

### List MCP servers

```
GET /mcp_servers?state={state}
```

| Parameter | In | Type | Required | Description |
| ----------- | ------ | ------ | ---------- | ------------- |
| `state` | query | string | No | Filter: `cold`, `ready`, `degraded`, `dead` |

**Response 200:**

```json
{
  "mcp_servers": [
    {
      "mcp_server_id": "math",
      "state": "ready",
      "mode": "subprocess",
      "alive": true,
      "tools_count": 5,
      "health_status": "healthy",
      "tools_predefined": false,
      "dead": null,
      "description": "Math computation mcp_server"
    }
  ]
}
```

`dead` is `null` unless the server is `dead`; then it says why, since when and
what starts it again. `description` is omitted when none is set.

### Create MCP Server

```
POST /mcp_servers
```

**Request body:**

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `mcp_server_id` | string | Yes | -- | Unique identifier |
| `mode` | string | Yes | -- | `subprocess`, `docker`, or `remote` |
| `command` | list[string] | For subprocess | -- | Command to run |
| `image` | string | For docker | -- | Docker image |
| `endpoint` | string | For remote | -- | HTTP endpoint URL |
| `env` | dict | No | `{}` | Environment variables |
| `idle_ttl_s` | int | No | `300` | Idle timeout in seconds |
| `health_check_interval_s` | int | No | `60` | Health check interval |
| `description` | string | No | -- | Human-readable description |
| `tls` | dict | No | -- | Remote only: `peer_identity` and `max_connection_age`. With `peer_identity` the server is key-pinned, needs `mcp_servers:peer_identity` and an `https` endpoint, and may omit `endpoint` |

*Since 2.34.2* a `mode` other than `remote` -- `subprocess`, `docker`,
`container`, or a value Hangar does not recognise -- also needs
`mcp_servers:local_launch`, which `admin` and `provider-admin` hold and
`developer` and `kubernetes-operator` do not; without it the route answers
`403`. See [Authentication](../guides/AUTHENTICATION.md#built-in-roles).

*Since 2.34.2* a `remote` server's `endpoint` must be an `http` or `https` URL
with a host; anything else (`file:///...`, a bare host name) is `422
ValidationError`. Before, it was stored and failed at every start.

The registration's provenance is always recorded as `api`; a `source` field in
the body is ignored. A body without `mcp_server_id` or `mode` is `400
missing_fields`, and an id that already exists is `422 ValidationError`.

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

**Response 200:** MCP Server detail object: `mcp_server_id`, `state`, `mode`,
`alive`, `tools` (tool objects, a withheld one shown as in
[Get MCP Server Tools](#get-mcp-server-tools)), `health` (the object
[Get MCP Server Health](#get-mcp-server-health) returns), `idle_time`, `meta`,
`provenance` and `dead`.

**Response 404:** MCP Server not found.

### Update MCP Server

```
PUT /mcp_servers/{mcp_server_id}
PATCH /mcp_servers/{mcp_server_id}
```

Both `PUT` and `PATCH` are accepted and behave identically (partial update).

**Request body (all fields optional):**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `description` | string | New description |
| `env` | dict | New environment variables (replaces existing) |
| `idle_ttl_s` | int | New idle timeout |
| `health_check_interval_s` | int | New health check interval |
| `endpoint` | string | New endpoint of a remote server; `null` clears it, which only a key-pinned server may have |
| `tls` | dict | New `tls` block of a remote server (`peer_identity`, `max_connection_age`) |

Setting `env` on a server that is not `remote` also needs
`mcp_servers:local_launch` (2.34.2+). Changing `endpoint` or `tls` needs a
durable configuration store, and on a key-pinned server, or adding a peer
identity, `mcp_servers:peer_identity`. An `endpoint` must be an `http` or
`https` URL with a host (`422` otherwise, 2.34.2+). A server declared in the
configuration file answers `409 declared_in_config`.

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

**Response 409** (2.26.0 and later): the server is declared in the gateway's
configuration file. Such a delete used to last only until the next reload or
restart. The server keeps running. Remove it from the configuration and
reload, or stop it with `POST /mcp_servers/{mcp_server_id}/stop`.

```json
{"error": "declared_in_config", "mcp_server_id": "math", "detail": "McpServer math is declared in the gateway configuration; ..."}
```

### Forget a Peer-Key Name

```
DELETE /mcp_servers/{mcp_server_id}/peer_identity
```

A key-pinned server's name keeps its peer-key record after the server is
deleted, so the name cannot come back as a plain server. This route removes
that record. It needs `mcp_servers:peer_identity`, and the server must already
be deleted: while it exists the route answers `422 PeerKeyNameTaken`, and a name
with no record is `404`.

**Response 200:**

```json
{"mcp_server_id": "payments", "forgotten": true}
```

### Start MCP Server

```
POST /mcp_servers/{mcp_server_id}/start
```

**Response 200:**

```json
{"mcp_server": "math", "state": "ready", "tools": ["add", "subtract"]}
```

### Stop MCP Server

```
POST /mcp_servers/{mcp_server_id}/stop
```

**Request body (optional):**

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `reason` | string | `"user_request"` | Reason for stopping |

**Response 200:**

```json
{"stopped": "math", "reason": "user_request"}
```

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
    {
      "name": "add",
      "description": "Add two numbers",
      "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}}},
      "digest": "e84e846a57adc93e...",
      "pinned_digest": "e84e846a57adc93e..."
    }
  ]
}
```

`digest` is the tool's SHA-256 fingerprint as listed -- the value
`mcp-hangar pin` computes. `pinned_digest` is present only when the tool has an
all-tenants pin (`tool_projection.pins`); a per-tenant pin is not shown here.
See [Digest Pinning](configuration.md#digest-pinning).

A tool a model is not shown is listed as its `name`, `digest`, `pinned_digest`
when it has one, and `withheld`, with no `description` and no `inputSchema`:

- `"digest_drift"` (2.30.0+): it drifted from a pin under
  `digest_enforcement: block`, for any tenant;
- `"withdrawn"` (2.34.2+): it is withdrawn for every tenant, on the server or a
  group that owns it, or `tool_projection.new_tools: withhold` is set and the
  pins do not admit it for every tenant. A tool pinned for some tenants only is
  shown withheld here too, because this route answers for no tenant. A
  withdrawal for some tenants only is not marked.

Read `withheld` before `description` or `inputSchema`.

### Get MCP Server Health

```
GET /mcp_servers/{mcp_server_id}/health
```

**Response 200:**

```json
{"consecutive_failures": 0, "total_invocations": 1, "total_failures": 0, "success_rate": 1.0, "can_retry": true, "last_success_ago": 0.07, "last_failure_ago": null}
```

### Get MCP Server Logs

```
GET /mcp_servers/{mcp_server_id}/logs?lines={n}
```

| Parameter | In | Type | Default | Range | Description |
| ----------- | ------ | ------ | --------- | ------- | ------------- |
| `lines` | query | int | `100` | 1--1000 | Number of recent lines; out-of-range values are clamped |

**Response 200:**

```json
{
  "logs": [
    {"mcp_server_id": "math", "stream": "stderr", "content": "...", "recorded_at": 1774260930.5}
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
| ----------- | ------ | ------ | --------- | ------- | ------------- |
| `limit` | query | int | `100` | 1--500 | Max records; out-of-range values are clamped |
| `from_position` | query | int | `0` | -- | Event store version to start from (inclusive) |

**Response 200:**

```json
{
  "mcp_server_id": "math",
  "history": [...],
  "total": 42
}
```

Each entry is a `ToolInvocationCompleted` or `ToolInvocationFailed` event.
`total` counts the entries returned, not every invocation in the stream; page
on with `from_position`.

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
      "description": "LLM pool",
      "state": "healthy",
      "strategy": "round_robin",
      "min_healthy": 1,
      "healthy_count": 1,
      "members_in_rotation_count": 2,
      "total_members": 2,
      "is_available": true,
      "circuit_open": false,
      "members": [...]
    }
  ]
}
```

Each entry is the group's status, read at one instant. `state` is the group's availability (`inactive`, `partial`, `healthy`, `degraded`), not a server lifecycle state. `healthy_count` counts the members that are `ready` and in rotation; `members_in_rotation_count` counts the members in rotation in any state. A group whose members are all `cold` reads `healthy_count: 0` and still routes while `is_available` is `true`. See [Group States](../guides/MCP_SERVER_GROUPS.md#group-states).

### Create Group

```
POST /groups
```

**Request body:**

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
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

**Response 200:** The same object as one entry of `GET /groups`; `hangar_details` returns the same for a group.

### Update Group

```
PUT /groups/{group_id}
```

**Request body (all optional):**

| Field | Type | Description |
| ------- | ------ | ------------- |
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
| ------- | ------ | ---------- | --------- | ------------- |
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

> **Preview — source management.** Registering, updating, deleting, scanning, and
> enabling/disabling a discovery source (every endpoint below except *List Sources*)
> ships in 2.5.0 as **Preview**, not GA: the behaviour may still change. Each of
> those responses carries the header `X-Hangar-Preview: discovery-source-management`
> so a client can detect the preview status programmatically. *List Sources* and the
> approval workflow are stable.

### List Sources

```
GET /discovery/sources
```

**Response 200:**

```json
{
  "sources": [
    {
      "id": "28018ad1-4d9d-54dc-9e4e-c5d856af4612",
      "source_type": "docker",
      "mode": "additive",
      "is_healthy": true,
      "is_enabled": true,
      "last_discovery": "2026-08-08T09:22:56+00:00",
      "mcp_servers_count": 3,
      "error_message": null
    }
  ]
}
```

`id` is the value every other route on this resource takes -- `/scan`,
`/enable`, `PUT` and `DELETE`. For a source declared in `config.yaml` it is
derived from the source type rather than generated, so it is the same id after a
restart and a script can keep using it. *Since 2.5.0:* before that, configured
sources were listed without an `id` and the scan answered `404` for anything an
operator could obtain.

The listing carries an `id` only while the discovery registry still knows the
source -- this route strips it from any source the orchestrator keeps running
after a `DELETE`, so a listed id is always one the per-source routes accept,
where the [`hangar_sources`](tools.md#hangar_sources) MCP tool returns the raw
status and can keep reporting an id these routes now answer `404` for.
*Since 2.5.0.*

`last_discovery` is `null` until the first cycle completes, and `error_message`
carries the last failure or `null`.

### Register Source

```
POST /discovery/sources
```

**Request body:**

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `source_type` | string | Yes | -- | `docker`, `filesystem`, `kubernetes`, `entrypoint` |
| `mode` | string | Yes | -- | `additive` or `authoritative` |
| `enabled` | bool | No | `true` | Activate immediately |
| `config` | dict | No | `{}` | Source-specific configuration |

**Response 201:**

```json
{"source_id": "...", "registered": true}
```

The source is built and added to the running discovery cycle, so *List
Sources* shows it under the returned `source_id` and the cycle scans it. The
cycle holds one source per type and the id is derived from the type, so a type
already held -- from the configuration or an earlier call -- is `422
ValidationError` (`A '<type>' discovery source is already held; update it
instead of registering another`), as is a type that is unknown or whose
dependencies are not installed. A `mode` other than `additive` or
`authoritative` is `400 invalid_mode`.

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
{"pending": [{"name": "new-mcp-server", "source_type": "docker", "mode": "remote", "connection_info": {...}, "fingerprint": "...", "ttl_seconds": 90, ...}]}
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

Approves a quarantined MCP server, or one pending approval because its source
has `auto_register: false` (the ones `GET /discovery/pending` lists).

**Response 200:** `{"approved": true, "mcp_server": "...", "status": "registered"}` on success. A
name in neither place also answers `200`, with
`{"approved": false, "mcp_server": "...", "error": "McpServer not found in quarantine or pending"}`.

### Reject MCP Server

```
POST /discovery/reject/{name}
```

Rejects a quarantined or pending MCP server.

**Response 200:** `{"rejected": true, "mcp_server": "..."}`, or `"rejected": false` with the
same `error` when the name is in neither place.

---

## Configuration

### Get Config

```
GET /config
```

Returns the MCP server records the durable configuration repository holds --
the registrations a persistence backend keeps across a restart -- redacted.
*Since 2.34.2* the redaction reaches every level: a value under a sensitive key
name (`env` entries such as `API_KEY` or `DB_PASSWORD` included) and a
credential-shaped value are replaced. Before 2.34.2 only top-level keys were
checked, so every server's `env` was served as stored. It is not the running
configuration: on a gateway
without a durable persistence backend it answers `{"config": {}}`. For the
running state use [Export Config](#export-config).

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
| ------- | ------ | --------- | ------------- |
| `graceful` | bool | `true` | Graceful reload |

Sending `config_path` is **refused** with `422` and
`config_path is not accepted; reload always targets the server's own
configuration file`. Reload re-reads the file the process was started with;
there is no way to point it at another one over HTTP.

**Response 200:**

```json
{"status": "reloaded", "result": {"success": true, "config_path": "...", "mcp_servers_added": [], "mcp_servers_removed": [], "mcp_servers_updated": [], "mcp_servers_unchanged": ["math"], "duration_ms": 3.9}}
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
rotating older ones to `.bak2` and beyond. *Since 2.29.0* the file this route
(and [Config Diff](#config-diff)) reads is the one the gateway was started
with, as for reload; `MCP_CONFIG`, or `config.yaml` in the working directory,
is only the fallback for a gateway built from a dict, which has no file. A
`config_path` field in the body (or, for the diff, a `config_path` query
parameter) is refused with `422`. Before 2.29.0 both routes read `MCP_CONFIG`
or `./config.yaml` whatever `--config` said, and took a caller-supplied
`config_path`. The returned `path` is relative when that name is.

That directory has to be writable by the process, and in the published
container image it is not: `/app` is owned by root and the gateway runs as
`hangar`.

*Since 2.5.0* that answers **503** with the reason --
`could not write the backup beside 'config.yaml': Permission denied` -- rather
than a bare `500` and `An internal server error occurred.`. Mount a writable
directory and start the gateway with its configuration file in it if you need
this endpoint.

### Config Diff

```
GET /config/diff
```

Compares on-disk configuration with current in-memory state. *Since 2.34.2*
both sides are redacted as [Get Config](#get-config) redacts, before the diff
is computed, so neither `diff` nor `on_disk` nor `in_memory` carries a secret
value. Before, the on-disk side was served after `${VAR}` interpolation,
secrets included.

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
    },
    "capabilities": ["peer_identity", "declared_key_issuance"]
  }
}
```

The counter is `total_invocations`, not `total_tool_calls`. `instance` is
present from 2.5.0 and describes the replica that answered -- see
[Running more than one replica](../cookbook/25-multiple-replicas.md). With a
coordination lease keeper, `instance` also carries `management_lease`
(`holder`, `generation`, `expires_in_s`, `my_lease_ttl_s`), or `null` while no
lease is seen. `capabilities` names what a client may rely on this core to
enforce: `peer_identity` (key-pinned servers, 2.32.0+) and
`declared_key_issuance`.

### Get Current User

```
GET /system/me
```

Returns the current authentication status. Used by the SPA to check whether a user is logged in. When auth is not enabled, returns `authenticated: false`.

**Response 200:**

```json
{"authenticated": true, "principal": {"id": "service:my-app", "type": "service_account"}}
```

`type` is `service_account` for an API-key principal and `user` for an OIDC
identity.

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
    {"mcp_server_id": "math", "tool_name": "add", "description": "Add two numbers", "input_schema": {"type": "object", "properties": {"a": {"type": "number"}}}, "digest": "e84e846a...", "pinned_digest": "e84e846a..."}
  ]
}
```

`input_schema` is the tool's input schema as a JSON object (since 2.28.0).
`digest` and `pinned_digest` are as described there. A withheld tool carries
`withheld` (`"digest_drift"`, or `"withdrawn"` since 2.34.2) and no
`description` or `input_schema`, as on
[Get MCP Server Tools](#get-mcp-server-tools). Only
servers whose tools are known appear: a `cold` server without predefined tools
contributes nothing until it has started.

---

## Sessions

### Suspend Session

```
POST /sessions/{session_id}/suspend
```

Adds a session to the suspended registry of the replica that answers and
announces it, so the other replicas apply it too. A `session_id` that is not
1-128 letters, digits, dashes or underscores is `400`.

**Request body (optional):**

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
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

Every route here requires the `admin` role. With authentication disabled they
are not wired and answer `503`, with the generic `InternalServerError` body;
`GET /auth/permissions` is a static list and answers `200` either way.

*Since 2.25.0* the actor of every change -- the creator of a key or role, the
revoker, the assigner, the updater, the deleter -- is the principal that
authenticated the request. It is recorded in the domain event, the log line
and, for a new key, the response. A body that still carries `created_by`,
`revoked_by`, `assigned_by` or `updated_by`, whatever its value (`null` and
the caller's own id included), is refused with `422` and a `ValidationError`
naming the field, and nothing is changed
([mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)).
Before 2.25.0 those fields were accepted, defaulted to `"system"`, and were
recorded as written, so an event from an older gateway names whoever the body
said.

### Create API Key

```
POST /auth/keys
```

**Request body:**

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `principal_id` | string | Yes | -- | Principal this key authenticates as |
| `name` | string | Yes | -- | Human-readable key name |
| `expires_at` | string | No | -- | ISO8601 expiry datetime |

**Response 201:**

```json
{"key_id": "...", "raw_key": "mcp_...", "principal_id": "...", "name": "...", "created_by": "user:alice", "expires_at": null, "warning": "Save this key now - it cannot be retrieved later!"}
```

`created_by` is the caller's principal id. *Since 2.34.2* a body missing
`principal_id` or `name` is `400 missing_fields` (before, a `500`), an
`expires_at` without a UTC offset is read as UTC, and one that does not parse
is `422 ValidationError`.

!!! warning
    The `raw_key` is returned only once. Store it securely.

### Revoke API Key

```
DELETE /auth/keys/{key_id}
```

**Request body (optional):**

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `reason` | string | `""` | Revocation reason |

### List API Keys

```
GET /auth/keys
```

| Parameter | In | Type | Required | Description |
| ----------- | ------ | ------ | ---------- | ------------- |
| `principal_id` | query | string | Yes | Principal whose keys to list |
| `include_revoked` | query | bool | No | Include revoked keys (default `true`) |

**Response 200:** `{"principal_id": "...", "keys": [{"key_id", "name", "created_at", "expires_at", "last_used_at", "revoked"}], "total": 1, "active": 1}`.
Without `principal_id` the route answers `400` with
`{"error": {"code": "ValidationError", "message": "principal_id is required"}}`.

### List All Roles

```
GET /auth/roles/all
```

| Parameter | In | Type | Required | Description |
| ----------- | ------ | ------ | ---------- | ------------- |
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

**Request body:** `role_name` (required), `description`, and `permissions` -- a
list of `resource:action` or `resource:action:id` strings.

**Response 201:** `{"role_name": "ops", "description": "...", "permissions_count": 2, "created": true, ...}`.

### Update Custom Role

```
PATCH /auth/roles/{role_name}
```

**Request body:** `permissions` (replaces the list) and `description`.

### Delete Custom Role

```
DELETE /auth/roles/{role_name}
```

**Response 204**, no body. A built-in role is `403 CannotModifyBuiltinRoleError`;
an unknown one is `404`. The caller is recorded as `deleted_by`.

### Assign Role

```
POST /auth/roles/assign
```

**Request body:**

```json
{"principal_id": "...", "role_name": "developer", "scope": "global"}
```

### Revoke Role

```
DELETE /auth/roles/revoke
```

**Request body:**

```json
{"principal_id": "...", "role_name": "developer", "scope": "global"}
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
| ----------- | ------ | ------ | ---------- | ------------- |
| `principal_id` | query | string | Yes | Principal whose roles to list |
| `scope` | query | string | No | Scope filter (default `*` = all) |

### List Permissions

```
GET /auth/permissions
```

Returns a fixed manifest of resource types and actions.

**Response 200:**

```json
{"permissions": [{"resource_type": "provider", "actions": ["read", "write", "invoke", "admin"]}, {"resource_type": "group", "actions": ["read", "write", "admin"]}, "..."]}
```

The manifest is static and does not list the permissions route enforcement
checks (see [Required permissions](#required-permissions)); read a role's
actual grants with `GET /auth/roles/{role_name}`.

### Check Permission

```
POST /auth/check-permission
```

**Request body:**

```json
{"principal_id": "...", "permission": "mcp_servers:lifecycle"}
```

`permission` is `resource:action[:id]`. Alternatively send `action`,
`resource_type` and `resource_id` separately.

**Response 200:**

```json
{"principal_id": "...", "action": "lifecycle", "resource_type": "mcp_servers", "resource_id": "*", "allowed": false, "granted_by_role": null}
```

### Get Tool Access Policy

```
GET /auth/policies/{scope}/{target_id}
```

| Parameter | In | Type | Required | Description |
| ----------- | ------ | ------ | ---------- | ------------- |
| `scope` | path | string | Yes | `provider`, `group`, or `member` |
| `target_id` | path | string | Yes | Identifier of the provider, group, or member |

Any other `scope` is `400 ValidationError`. **Response 200:**
`{"found": true, "scope": "provider", "target_id": "math", "allow_list": [...], "deny_list": [...]}`;
`found` is `false` with empty lists when no policy is set.

### Set Tool Access Policy

```
POST /auth/policies/{scope}/{target_id}
```

**Request body:**

```json
{"allow_list": ["tool_a", "tool_b*"], "deny_list": ["tool_c"]}
```

**Response 200:** the stored policy with `"set": true`.

### Clear Tool Access Policy

```
DELETE /auth/policies/{scope}/{target_id}
```

**Response 204**, no body.

---

## L7 Egress Policy

Read, attach, replace, or clear the L7 egress policy (compiled `MCPEgressPolicy`)
on a single MCP server. The core policy engine and this REST intake are available
in v1.6.0; end-to-end delivery from a Kubernetes `MCPEgressPolicy` custom
resource needs the operator's controller to compile and push the policy, which
ships in operator v0.14.0 and later. L7 egress is the **last** gate on the
invocation path, evaluated inside `invoke_tool` immediately before the upstream
call.

These routes are gated on `policy:read` / `policy:write`, **not** on
`mcp_servers:write`. The distinction is deliberate: `mcp_servers:write` is held
by `developer`, and gating policy mutation on it let that role clear an egress
policy. Among the built-in roles `policy:read` and `policy:write` are held by
`admin`, `provider-admin` and `kubernetes-operator` only.

### Get L7 Policy

```
GET /mcp_servers/{mcp_server_id}/l7_policy
```

Returns the attached policy in the same wire form `POST` accepts. Requires
`policy:read`.

**Response 200:** the compiled policy body, with every section filled in and a
`policyId` (`sha256:...`) added.

**Response 404:** `{"error": "no_l7_policy", "mcp_server_id": "math"}` when the
MCP server exists but holds no policy.

### Set L7 Policy

```
POST /mcp_servers/{mcp_server_id}/l7_policy
PUT  /mcp_servers/{mcp_server_id}/l7_policy
```

Attaches or replaces the compiled L7 policy on an MCP server. `POST` and `PUT`
behave identically. Requires `policy:write`.

**Request body:** the compiled policy the operator derives from an
`MCPEgressPolicy`:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `tools` | dict | Tool-name globs: `allow`, `deny`, `requireApproval` |
| `headers` | dict | Header rules: `allow`, `deny`, `requireApproval` |
| `arguments` | dict | Argument-level constraints: `secretPatterns`, `maxPayloadBytes` |
| `defaultAction` | string | `Allow` or `Deny` when no rule matches; default `Deny` |
| `mode` | string | `Audit` or `Enforce`; anything else, or absent, is `Enforce` |

> **What `requireApproval` does depends on whether an approval gate is
> configured.** With one, the match holds the call and waits for a human
> decision or the gate's `approval_timeout_seconds` — the egress policy is the
> second, independent source of "ask a human" beside the tool-access
> [`approval_list`](configuration.md#holding-a-tool-for-a-human-approval_list),
> and both resolve through the same gate. With no gate configured it stays
> fail-closed: the call is blocked, indistinguishable from a deny. The two
> controls are still declared separately — an egress `requireApproval` match
> does not read `approval_list`.

**Response 200:**

```json
{"mcp_server_id": "math", "l7_policy_set": true, "persisted": true}
```

`persisted` (*since core 2.22.1*) says whether a restart of this gateway gives
the policy back. It is `false` when the gateway has no durable persistence
backend, or keeps one but does not read it back at start
(`MCP_AUTO_RECOVER=false`); each such push also logs `l7_policy_not_persisted`
at warning. It reports the configuration, not the storage: SQLite on a volume
that does not outlive the pod reports `true`. See
[Surviving a gateway restart](../guides/EGRESS_POLICY.md#surviving-a-gateway-restart).

**Response 400:** `{"error": "invalid_l7_policy", "detail": "..."}` when the body
is not a valid compiled policy.

**Response 404:** MCP Server not found.

### Clear L7 Policy

```
DELETE /mcp_servers/{mcp_server_id}/l7_policy
```

Clears the L7 policy on an MCP server, disabling L7 enforcement for it. Requires
`policy:write`.

**Response 200:**

```json
{"mcp_server_id": "math", "l7_policy_set": false, "persisted": true}
```

`persisted` is always `true` here: a gateway that keeps nothing starts with no
policy, so a restart keeps the policy cleared either way.

---

## Admin Tools

Runtime tool withdrawal/restore. Requires `mcp_servers:lifecycle`, which the
built-in `admin`, `provider-admin`, `developer` and `kubernetes-operator` roles
hold. *Since 2.29.0* a withdrawal or restore for every tenant -- no
`tenant_id` -- also needs `admin` (`*:*`), so a global `developer` gets `403`
unless it names a tenant. A grant held only within a tenant acts on its own
tenant: omitting `tenant_id` means that tenant, and naming another is `403`.

### Withdraw Tool

```
POST /admin/tools/{server}/{tool}/withdraw
```

Withdraws a tool at runtime. The withdrawal is recorded, so it survives a
config reload **and** a restart, and it reaches every replica in the fleet
rather than only the one that served this request.

*Before 2.17.1 it lived in the memory of the replica that took the call: the
other replicas kept listing and serving the tool, and a rolling restart lifted
it entirely.* Propagation to peers is not instantaneous -- a peer applies the
withdrawal when it reads the event, within one tail interval.

**Request body (optional):**

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `tenant_id` | string | `null` | Tenant to withdraw for. Omit/null withdraws for all tenants (needs `admin`) |
| `kind` | string | `"tool"` | `tool`, `prompt` or `resource`; anything else is `400 invalid_kind`. A resource is named by its uri, slashes included |

**Response 200:**

```json
{"withdrawn": true, "mcp_server": "math", "tool": "add", "kind": "tool", "tenant_id": null}
```

### Restore Tool

```
POST /admin/tools/{server}/{tool}/restore
```

Removes a runtime withdrawal (config-declared withdrawals persist independently).

**Request body (optional):**

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `tenant_id` | string | `null` | Tenant to restore. Omit/null removes the entire runtime entry (needs `admin`) |
| `kind` | string | `"tool"` | As for withdraw |

**Response 200:**

```json
{"restored": true, "mcp_server": "math", "tool": "add", "kind": "tool", "tenant_id": null}
```

### Tool Pin History

```
GET /admin/tools/pins?tool={name}&server={id}
```

The recorded and revoked pins of one tool, oldest first, read from the event
store. `tool` is required (`400` without it); `server` narrows it to one server.
Needs `audit:read`. A grant held only within a tenant sees the pins recorded
for its own tenant, and not those for all tenants. Without an event store the
route answers `503`.

**Response 200:**

```json
{"tool": "add", "pins": [{"event": "recorded", "occurred_at": 1774260930.5, "mcp_server_id": "math", "tool": "add", "tenant_id": null, "sha256": "e84e...", "source": "config", "previous_sha256": null, "upstream": null, "structure_sha256": "...", "description_sha256": "...", "approved_by": "config"}]}
```

A `revoked` entry carries `revoked_by` in place of the last five fields.

---

## Approvals

Available when the approval service is enabled. Paths below are the 2.x routes, served under the `/api` mount — verified against core's published route inventory (`api-routes.json`). On the closed 1.6.x line these lived under `/enterprise/approvals`.

These routes became usable in **2.1.0**. Before that they read an application-state field that nothing ever populated, so `GET /api/approvals` answered `500` with an `AttributeError` on every deployment ([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678)). The service is now published onto application state from a single place shared by the HTTP-serve path, the server factory and any test client, and the routes fall back to the application context — the same object the enforcement path reads — so the API and enforcement cannot hold different services. When there is genuinely no gate service, these routes answer **503**, not a stack trace.

Something has to put a tool behind the gate before anything appears here: see [`approval_list`](configuration.md#holding-a-tool-for-a-human-approval_list).

### List Approvals

```
GET /approvals?state={state}&provider_id={id}
```

| Parameter | In | Type | Default | Description |
| ----------- | ------ | ------ | --------- | ------------- |
| `state` | query | string | `pending` | Filter: `pending`, `approved`, `denied`, `expired`, `cancelled` (2.25.0) |
| `provider_id` | query | string | -- | Optional provider filter |

**Response 200:** a bare JSON array of approval request objects, each with
`approval_id`, `provider_id`, `tool_name`, `arguments`, `state`, `channel`,
`requested_at`, `expires_at`, `expires_in_seconds`, `requested_by`,
`decided_by`, `decided_at`, `reason` and `tenant_id`. An unknown `state` is
`400`.

### Get Approval

```
GET /approvals/{approval_id}
```

**Response 200:** Approval request object.

**Response 404:** Approval not found.

### Resolve Approval

```
POST /approvals/{approval_id}/resolve
```

Approves or denies a pending approval. Requires an authenticated principal holding `approval:resolve`; the decision is attributed to that principal.

From 2.0.0 this is the **only** way in. The Slack HMAC callback branch was removed, and the client-supplied `x-principal-id` header no longer sets identity. A Slack integration now runs as a delivery adapter that verifies the vendor signature itself and calls this endpoint with an ordinary token — see [Approval delivery adapters](../guides/APPROVAL_ADAPTERS.md).

On a gateway with auth disabled the decision is attributed to the system principal rather than refused: refusing there would decide nothing.

**Request body:**

| Field | Type | Required | Description |
| ------- | ------ | ---------- | ------------- |
| `decision` | string | Yes | `approve` or `deny` |
| `reason` | string | No | Optional resolution reason |

**Response 200:** `{"approval_id": "...", "state": "approved"}` (or `denied`).
A `decision` other than `approve` or `deny` is `400`; an approval that is
already resolved is `409` with its `state`.

*Since 2.25.0* an approval for a held call whose `hangar_call` batch deadline
has already passed is refused: the call will not run, so there is nothing to
let through. The answer is `409`:

```json
{"error": "Approval refused: the held call was cancelled and did not run", "state": "cancelled"}
```

The record moves to the terminal state `cancelled`, and the gate publishes
`ToolApprovalCancelled`, whose `attempted_by` names the approver, instead of
`ToolApprovalGranted`. On a `cancelled` record `decided_by` names who tried to
approve the call, not who let it through. A client that reads every `409` as
"already resolved" should read `state`. A denial after the deadline is still
recorded as a denial. An approval that lands on a different gateway instance
from the held call still answers `200` there; the instance holding the call
records it `cancelled`
([mcp-hangar#1702](https://github.com/mcp-hangar/mcp-hangar/issues/1702)).

---

## WebSocket Endpoints

### Events Stream

```
ws://host:port/api/ws/events
```

Streams all domain events as JSON frames. Requires `audit:read`; a principal
without it is refused at the handshake (`403`). A grant held only within a
tenant receives only the events that name that tenant.

*Since 2.25.0* `websockets` is a dependency of `mcp-hangar`, so the endpoint
works on a `pip` or `uv` install as well as in the image. Before 2.25.0 only
the image installed a WebSocket library; on a `pip` install the upgrade was
answered `404` and uvicorn logged `No supported WebSocket library detected`
([mcp-hangar#1676](https://github.com/mcp-hangar/mcp-hangar/issues/1676)).

Credentials go in the upgrade request's headers. A client that cannot set
headers may pass a JWT as `?token=<jwt>`, read as `Authorization: Bearer <jwt>`
when neither that header nor the API-key header is present; an API key is not
accepted this way. A token in the URL can land in the access logs of any proxy
on the path.

The subscription is live from the moment the connection is accepted: events
published before the client's first `subscribe` message are queued and
filtered when they are sent, not dropped.

See the [WebSockets guide](../guides/WEBSOCKETS.md) for connection details.

---

## Outside `/api`

These are served at the root, not under the base URL, and skip authentication:

| Method | Path | Response |
| -------- | ------ | ---------- |
| `GET` | `/health/live` | `{"status": "healthy"}` |
| `GET` | `/health/ready` | `{"status": "healthy", "ready_mcp_servers": 1, "total_mcp_servers": 1}` |
| `GET` | `/health/startup` | `{"status": "healthy", "startup_complete": true, "uptime_seconds": 51.6}` |
| `GET` | `/metrics` | Prometheus text format |
| `GET` | `/.well-known/oauth-protected-resource` | RFC 9728 metadata; `404` when no OIDC issuer is configured |

The MCP protocol itself is served at `/mcp`.
