# MCP Tools Reference

Complete reference for the `hangar_*` MCP tools MCP Hangar serves to MCP clients (Claude Desktop, LM Studio, custom integrations). Which of them a client sees, and which it may call, depends on the topology mode, the transport and the caller's permissions. See [Who sees and calls which tool](#who-sees-and-calls-which-tool).

## Quick Reference

| Tool | Category | Description | Side Effects | Permission |
| ------ | ---------- | ------------- | -------------- | ------------ |
| [`hangar_list`](#hangar_list) | Lifecycle | List all MCP servers with state and tool counts | None (read-only) | `mcp_servers:read` |
| [`hangar_start`](#hangar_start) | Lifecycle | Start a MCP server or group | Starts process/container | `mcp_servers:lifecycle` |
| [`hangar_stop`](#hangar_stop) | Lifecycle | Stop a MCP server or group | Stops process/container | `mcp_servers:lifecycle` |
| [`hangar_status`](#hangar_status) | Lifecycle | Status dashboard of the replica that answers | None (read-only) | `mcp_servers:read` |
| [`hangar_reload_config`](#hangar_reload_config) | Lifecycle | Reload configuration from disk | Stops/starts MCP servers | `config:reload` |
| [`hangar_load`](#hangar_load) | Hot-Loading | Load MCP server from registry at runtime | Downloads and starts MCP server | `mcp_servers:write` |
| [`hangar_unload`](#hangar_unload) | Hot-Loading | Unload a hot-loaded MCP server | Stops and removes MCP server | `mcp_servers:write` |
| [`hangar_tools`](#hangar_tools) | MCP Server | List tools available on a MCP server | May start cold MCP server | `mcp_servers:read` |
| [`hangar_details`](#hangar_details) | MCP Server | Detailed MCP server or group information | None (read-only) | `mcp_servers:read` |
| [`hangar_warm`](#hangar_warm) | MCP Server | Pre-start MCP servers for faster first call | Starts MCP server processes | `mcp_servers:lifecycle` |
| [`hangar_health`](#hangar_health) | Health | Health summary of the replica that answers | None (read-only) | `mcp_servers:read` |
| [`hangar_metrics`](#hangar_metrics) | Health | MCP Server metrics in JSON or Prometheus format | None (read-only) | `metrics:read` |
| [`hangar_discover`](#hangar_discover) | Discovery | Trigger discovery scan across all sources | Updates pending MCP server list | `discovery:trigger` |
| [`hangar_discovered`](#hangar_discovered) | Discovery | List pending discovered MCP servers | None (read-only) | `discovery:read` |
| [`hangar_quarantine`](#hangar_quarantine) | Discovery | List quarantined MCP servers | None (read-only) | `discovery:approve` |
| [`hangar_approve`](#hangar_approve) | Discovery | Approve a pending or quarantined MCP server | Registers MCP server | `discovery:approve` |
| [`hangar_sources`](#hangar_sources) | Discovery | List discovery sources with id and health status | None (read-only) | `discovery:read` |
| [`hangar_group_list`](#hangar_group_list) | Groups | List all MCP server groups with member details | None (read-only) | `group:read` |
| [`hangar_group_rebalance`](#hangar_group_rebalance) | Groups | Rebalance group membership and reset circuit breaker | Re-checks members, resets circuit | `group:update` |
| [`hangar_call`](#hangar_call) | Batch and Continuation | Invoke tools on MCP servers (single or batch) | May start cold MCP servers | `tool:invoke`, checked per call |
| [`hangar_fetch_continuation`](#hangar_fetch_continuation) | Batch and Continuation | Fetch truncated response data | None (read-only) | `tool:invoke` |
| [`hangar_delete_continuation`](#hangar_delete_continuation) | Batch and Continuation | Delete cached continuation data | Removes cached response | `tool:invoke` |
| [`hangar_whoami`](#hangar_whoami) | Identity | Show the caller's principal, tenant, groups and roles | None (read-only) | None; needs an authenticated caller |

The Permission column is the `resource:action` a caller needs when authentication is on. Every tool except
`hangar_fetch_continuation`, `hangar_delete_continuation` and `hangar_whoami` needs it as a global grant: a role held only within
a tenant does not reach them, because they act on the whole fleet. `hangar_call` checks `tool:invoke` for each
call in the batch, so one batch can carry calls that run and calls that are refused.

## Who sees and calls which tool

With authentication off (`--unsafe-no-auth`, or no `auth` block) every caller may call every tool. With it on,
what a client sees depends on the topology mode (`tool_access.mode`) and the transport:

| Surface | `tools/list` shows | Calling a tool the caller may not call |
| --------- | -------------------- | ---------------------------------------- |
| `egress`, HTTP | All 23 `hangar_*` tools, to every authenticated caller | `isError: true`, text `Not authorized to call '<tool>': <resource>:<action> permission required` |
| `front_door`, HTTP | Only the `hangar_*` tools the caller may call, and `hangar_whoami` to every authenticated caller. Never `hangar_call` or the continuation tools: there the upstream tools are listed under their own names instead | JSON-RPC error `-32601`, the same as an unknown tool |
| stdio, no `auth.stdio.principal` | `egress`: all 23, each management tool refused with `Authentication required to call '<tool>'`. `front_door`: none | As above |
| stdio, with `auth.stdio.principal` | As over HTTP, decided on the declared principal's roles | As above |

An HTTP request with no valid credential is refused with `401` before any tool runs. On `front_door` a caller
holding the built-in `viewer` role sees ten tools: `hangar_list`, `hangar_status`, `hangar_details`,
`hangar_tools`, `hangar_health`, `hangar_metrics`, `hangar_group_list`, `hangar_discovered`, `hangar_sources` and
`hangar_whoami`.

**The `hangar_*` names are reserved on `front_door`.** *Since 2.34.2* an upstream tool named like one of the
gateway's own tools (`hangar_status`, `hangar_whoami`, `hangar_call`, ...) is not projected: the gateway's tool
keeps the name, and `flat_tool_name_reserved` is logged naming the server. Before 2.34.2 the name was listed twice
and a call of it went to the upstream. In `egress` mode a tool is always named with its server, so nothing
changes there.

## Error shapes

A `hangar_*` tool fails in one of three ways:

- **The tool ran and failed** (an unknown server, a bad continuation id). The result has `isError: true` and
  is the error payload every tool uses:
  `{"error": "unknown_mcp_server: nope", "error_type": "ValueError", "details": {}}`. Before 2.29.1 this payload
  came with `isError: false`, so a client had to read `error_type` to tell it from a normal result.
- **The call was refused before the tool ran**: authorization, or an invalid server id such as `bad id!`. The
  result has `isError: true` and one text block, `Error executing tool <tool>: <reason>`.
- **On `front_door`, a tool not listed for the caller**: JSON-RPC error `-32601`.

The first two both set `isError: true`; they differ by body, the three-key payload or one
`Error executing tool ...` text block. The `Errors:` lines below give the `error` text of the first kind.

## Lifecycle

### `hangar_list` {#hangar_list}

List all configured MCP servers, groups, and runtime (hot-loaded) MCP servers with current state, mode, and tool counts.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `state_filter` | `str \| None` | `None` | Keep only entries in this state: a server state (`"cold"`, `"ready"`, `"degraded"`, `"dead"`) filters servers, a group state (`"healthy"`, `"partial"`, `"inactive"`) filters groups. An unknown value returns empty lists, not an error |

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_servers` | `list[object]` | Configured MCP servers, group members included, with `mcp_server_id`, `state`, `mode`, `alive`, `tools_count`, `health_status`, `tools_predefined`, `dead`, and `description` when one is configured |
| `groups` | `list[object]` | Groups, each the same object [`hangar_group_list`](#hangar_group_list) returns: `group_id`, `description`, `state`, `strategy`, `min_healthy`, `healthy_count`, `members_in_rotation_count`, `total_members`, `is_available`, `circuit_open`, `members` |
| `runtime_mcp_servers` | `list[object]` | Hot-loaded MCP servers with `mcp_server`, `state`, `source`, `verified`, `ephemeral`, `loaded_at`, `lifetime_seconds`, `dead` |

`dead` is `null` unless the server's `state` is `dead`. Then it is the object [`hangar_details`](#hangar_details) reports: `reason` (`given_up`, `crashed`, `start_failed` or `capability_blocked`), `since`, `retry_allowed_at` and `revived_by`.

**Two state vocabularies.** A server's `state` is its lifecycle: `cold`, `initializing`, `ready`, `degraded`, `dead`. A group's `state` is its availability, computed from its members: `inactive`, `partial`, `healthy`, `degraded`. A group's `degraded` means its circuit breaker is open, not that it is failing health checks, and a group is never `cold`: its members are. The same holds wherever a group's `state` appears, in `hangar_start`, `hangar_stop`, `hangar_status`, `hangar_details` and `hangar_group_list`. See [Group States](../guides/MCP_SERVER_GROUPS.md#group-states).

**Group member counts.** `healthy_count` counts the members that are `ready` and in rotation. `members_in_rotation_count` counts the members in rotation in any state, the length of the `members_in_rotation` list `hangar_group_rebalance` returns. So `healthy_count` <= `members_in_rotation_count` <= `total_members`. A group whose members are all `cold`, such as one the GC reaped for being idle, reads `healthy_count: 0` and still routes: the next call through it starts a member. To ask whether a group can take a call, read `is_available`. `hangar_status` and `hangar_health` report the same count as `healthy_members`.

**Example:**

```json
// Request
{"state_filter": "ready"}

// Response
{
  "mcp_servers": [
    {"mcp_server_id": "math", "state": "ready", "mode": "subprocess", "alive": true,
     "tools_count": 4, "health_status": "healthy", "tools_predefined": false, "dead": null}
  ],
  "groups": [],
  "runtime_mcp_servers": []
}
```

### `hangar_start` {#hangar_start}

Start a MCP server or group. Transitions the MCP server from COLD to READY. A deliberate start also starts a `dead` server again, whatever made it dead, without waiting out its backoff.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server ID or Group ID |

**Side Effects:** Starts MCP server process or container. State transitions from COLD to READY.

**Returns:**

For a MCP server:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_server` | `str` | MCP Server ID |
| `state` | `str` | New state (typically `"ready"`) |
| `tools` | `list[str]` | Available tool names |

For a group:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `group` | `str` | Group ID |
| `state` | `str` | Group availability state: `inactive`, `partial`, `healthy` or `degraded` (circuit open). Not a server lifecycle state |
| `members_started` | `int` | Number of members started |
| `healthy_count` | `int` | Members that are `ready` and in rotation |
| `members_in_rotation_count` | `int` | Members in rotation, in any state |
| `total_members` | `int` | Total member count |

**Example:**

```json
// Request
{"mcp_server": "math"}

// Response
{"mcp_server": "math", "state": "ready", "tools": ["add", "subtract", "multiply", "divide"]}
```

Errors: `unknown_mcp_server: <id>` (`error_type: ValueError`) for a name that is neither a server nor a group.

### `hangar_stop` {#hangar_stop}

Stop a running MCP server or group.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server ID or Group ID |

**Side Effects:** Stops MCP server process or container. State transitions to COLD.

**Returns:**

For a MCP server:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `stopped` | `str` | MCP Server ID |
| `reason` | `str` | Stop reason |

For a group:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `group` | `str` | Group ID |
| `state` | `str` | Group availability state: `inactive`, `partial`, `healthy` or `degraded` (circuit open). Not a server lifecycle state |
| `stopped` | `bool` | `true` |

**Example:**

```json
// Request
{"mcp_server": "math"}

// Response
{"stopped": "math", "reason": "user_request"}
```

Errors: `unknown_mcp_server: <id>` (`error_type: ValueError`)

### `hangar_status` {#hangar_status}

Human-readable status dashboard of the replica that answers the call, with state indicators for its MCP servers and groups.

**Scope: replica-local.** With more than one gateway replica, the answer describes the replica named in `replica.instance_id`, not the fleet. Under session affinity you do not choose which replica answers. Two calls can therefore reach two replicas and report different server states and uptimes without anything in the fleet having changed. Compare `replica.instance_id` before reading a difference as a change.

- **Same snapshot as `hangar_health`.** From one replica, the two tools agree. `hangar_health.mcp_servers.total` equals `summary.total_mcp_servers`, and both count hot-loaded servers.
- **One name per replica.** `replica.instance_id` is the identity the management lease reports as `holder`, `GET /system` reports as `instance.instance_id`, and traces carry as `service.instance.id`. See [Running more than one replica](../cookbook/25-multiple-replicas.md).
- **No fleet view here.** Neither tool asks other replicas or reads shared state. For a fleet-wide view, query the per-replica metrics in Prometheus, which scrapes every replica.

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_servers` | `list[object]` | MCP servers with `id`, `indicator`, `state`, `mode`, `dead`, and a `note` when there is something to say (a cold server's `Will start on first request`, a dead server's reason) |
| `groups` | `list[object]` | Groups with `id`, `indicator`, `state`, `healthy_members`, `total_members` |
| `runtime_mcp_servers` | `list[object]` | Hot-loaded MCP servers with `id`, `indicator`, `state`, `source`, `verified`, `dead` |
| `summary` | `object` | Counts: `healthy_mcp_servers`, `total_mcp_servers`, `runtime_mcp_servers`, `runtime_healthy`, plus `uptime` and `uptime_seconds`, which are the answering replica's process uptime (the same values as `replica.*`) |
| `replica` | `object` | The replica that answered: `instance_id`, `uptime_seconds`, `uptime` |
| `scope` | `str` | Always `"replica"` |
| `scope_note` | `str` | The same scope, stated in words |
| `formatted` | `str` | Pre-formatted text dashboard, headed by the replica that answered |

Indicator values come from two vocabularies, and `formatted` shows servers and groups in separate sections:

- Servers (`mcp_servers`, `runtime_mcp_servers`) have a lifecycle state: `[READY]`, `[COLD]`, `[STARTING]` (state `initializing`), `[DEGRADED]`, `[DEAD]`.
- Groups have an availability state computed from their members: `[HEALTHY]`, `[PARTIAL]`, `[INACTIVE]`, `[DEGRADED]`. A group's `[DEGRADED]` means its circuit breaker is open. Each `groups` entry also carries `circuit_open` (`bool`), which `formatted` shows in its `CIRCUIT` column, and `members_in_rotation_count` (`int`). Its `healthy_members` is the group's `healthy_count`: members that are `ready` and in rotation.

**Example:**

```json
// Request
{}

// Response
{
  "mcp_servers": [
    {"id": "math", "indicator": "[READY]", "state": "ready", "mode": "subprocess", "dead": null}
  ],
  "groups": [],
  "runtime_mcp_servers": [],
  "summary": {"healthy_mcp_servers": 1, "total_mcp_servers": 1, "uptime": "2h 15m"},
  "replica": {"instance_id": "hangar-0-3fa81c2e", "uptime_seconds": 8100.0, "uptime": "2h 15m"},
  "scope": "replica",
  "scope_note": "This describes what the replica named in replica.instance_id knows, not the fleet. ...",
  "formatted": "Answered by replica: hangar-0-3fa81c2e\n..."
}
```

### `hangar_reload_config` {#hangar_reload_config}

Reload configuration from disk, applying MCP server additions, removals, and updates.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `graceful` | `bool` | `true` | `true` waits, up to 30 s in all, for the calls in flight to the MCP servers the reload stops or rebuilds, then stops them; `false` stops them at once and those calls fail. Recorded on the `ConfigurationReloadRequested` event (`force` is its inverse). Since 2.28.0 |

**Side Effects:** Stops removed/modified MCP servers, registers new MCP servers, updates changed MCP servers. On `front_door`, then starts the added and changed servers in the background. A call made while another reload runs waits for it. See [Hot-Reload](hot-reload.md).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `status` | `str` | `"success"` |
| `message` | `str` | Human-readable result description |
| `mcp_servers_added` | `list[str]` | Newly added MCP server IDs |
| `mcp_servers_removed` | `list[str]` | Removed MCP server IDs |
| `mcp_servers_updated` | `list[str]` | Updated MCP server IDs |
| `mcp_servers_unchanged` | `list[str]` | Unchanged MCP server IDs |
| `duration_ms` | `float` | Reload duration in milliseconds |

A failed reload answers with the [error payload](#error-shapes): `error` is `Configuration reload failed: <reason>` and `error_type` names the exception, for example `ConfigurationError`. Nothing is applied.

**Example:**

```json
// Request
{"graceful": true}

// Response
{
  "status": "success", "message": "Configuration reloaded successfully",
  "mcp_servers_added": ["new-api"], "mcp_servers_removed": [],
  "mcp_servers_updated": ["math"], "mcp_servers_unchanged": ["filesystem"],
  "duration_ms": 45.2
}
```

## Hot-Loading

### `hangar_load` (async) {#hangar_load}

Load a MCP server from the MCP registry at runtime. Hot-loaded MCP servers are ephemeral and lost on server restart.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `name` | `str` | required | Registry name of the MCP server |
| `force_unverified` | `bool` | `false` | Load an entry outside the operator's `hot_loading.trusted_namespaces`. Ignored unless the operator set `hot_loading.allow_force_unverified: true` |
| `allow_tools` | `list[str] \| None` | `None` | Fnmatch patterns for allowed tools |
| `deny_tools` | `list[str] \| None` | `None` | Fnmatch patterns for denied tools |
| `approval_tools` | `list[str] \| None` | `None` | Fnmatch patterns for tools that stay visible but wait for a human approval before each call. Refused when the deployment has no approval gate |

**Side Effects:** Downloads and starts the MCP server process. Adds to the runtime registry.

Since 2.25.0 a policy that fails to parse -- an empty pattern in `allow_tools`, `deny_tools` or `approval_tools`, or a value that is not a list -- refuses the load before anything is installed or started. Before, the server was installed and started first, and stayed loaded with no policy ([mcp-hangar#1718](https://github.com/mcp-hangar/mcp-hangar/issues/1718)).

**Returns:**

The primary success response:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `status` | `str` | `"loaded"` |
| `message` | `str` | Result description |
| `mcp_server_id` | `str` | Assigned MCP server ID; pass it to `hangar_unload` |
| `mcp_server_name` | `str` | Registry name of the loaded server |
| `tools` | `list[str]` | Available tool names |
| `warnings` | `list[str]` | Present only when there is something to warn about. On a front door (`tool_access.mode: front_door`) it always says that the front door does not serve the loaded server, and that declaring it in `config.yaml` is the way to serve it there |

Other possible `status` values, each with a `message`: `"ambiguous"` (several registry entries match the name, listed in `matches`), `"not_found"` (no match in the registry), `"missing_secrets"` (required secrets not configured, with `mcp_server_name`, a `missing` list and `instructions`), `"unverified"` (MCP server not verified, with `mcp_server_name` and `instructions`; `force_unverified` overrides it only where `hot_loading.allow_force_unverified` is `true`), `"already_loaded"` (with the existing `mcp_server_id`, and on a front door the same `warnings` as a load), `"failed"` (hot-loading is not configured, no installable package or runtime for this server, or `approval_tools` asked for with no approval gate configured).

A short name often matches several registry entries: `filesystem` and `time` both answer `"ambiguous"`. Pass a name from `matches`.

**On a front door.** The front door lists and routes only the servers the configuration declares. A hot-loaded server's tools are not listed in `tools/list`, and a flat call of one answers `-32601`. *Since 2.34.4* `hangar_load` says so in `warnings` instead of answering `loaded` with no hint of it. The load itself is unchanged, and an `egress` gateway answers as before.

**Example:**

```json
// Request
{"name": "<registry name>", "allow_tools": ["read_*"]}

// Response
{"status": "loaded", "message": "...", "mcp_server_id": "filesystem", "mcp_server_name": "filesystem",
 "tools": ["read_file", "read_directory"]}
```

### `hangar_unload` {#hangar_unload}

Unload a hot-loaded MCP server. Only works for MCP servers loaded via `hangar_load`.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server ID (from `hangar_load` result) |

**Side Effects:** Stops the MCP server process and removes it from the runtime registry.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `status` | `str` | `"unloaded"`, `"not_hot_loaded"` (a configured server, or a name Hangar does not know), or `"failed"` (hot-loading is not configured) |
| `mcp_server` | `str` | MCP Server ID |
| `message` | `str` | Result description |
| `lifetime_seconds` | `float` | How long the MCP server was loaded (success only) |

**Example:**

```json
// Request
{"mcp_server": "filesystem"}

// Response
{"status": "unloaded", "mcp_server": "filesystem", "message": "Successfully unloaded 'filesystem'",
 "lifetime_seconds": 3600.5}
```

## MCP Server

### `hangar_tools` {#hangar_tools}

List the tools available on a MCP server or group. Tool access filtering (allow_list/deny_list) is applied.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server ID or Group ID |

**Side Effects:** May start a cold MCP server named directly, to discover its tools. It lists a `dead` server without starting it. A group's listing starts nothing.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_server` | `str` | MCP Server ID |
| `state` | `str` | MCP server state |
| `predefined` | `bool` | Whether tools are predefined (not discovered at runtime) |
| `tools` | `list[object]` | Tools with `name`, `description`, `inputSchema`, `digest` (the SEP-1766 SHA-256 fingerprint of the tool's schema, the value [digest pinning](configuration.md#digest-pinning) compares), and `pinned_digest` when a pin is declared |

`pinned_digest` is the pin declared for the caller's tenant, or for all tenants, on this id or on the group member
that served the listing; it is absent when none is. Under `digest_enforcement: warn` or `audit` a tool that drifted
is listed and the two digests differ. Under `block` a drifted tool is not listed at all: a call of it is refused,
and listing it would hand the model the drifted description. [`hangar_details`](#hangar_details) names it under
`withheld_tools`.

For a group, the response carries `group: true` in place of `predefined`. *Since 2.34.1* it lists a tool only when
every member a call from this caller may be routed to allows it (the member the caller is pinned to alone,
otherwise every member in rotation), and reads the catalogue a member in rotation already discovered: it selects
no member, advances no load-balancing strategy and starts nothing. It has no `state`, except `"dead"` with an
empty `tools` list when every routable member is dead. A group with no member in rotation, such as one whose
members were all stopped, answers `{"mcp_server": "<group>", "group": true, "tools": []}`; `hangar_warm`, or a
call through the group, brings a member into rotation. Before 2.34.1 a group listing selected and started a
member, and a group with nobody in rotation answered `no_healthy_members_in_group: <id>`.

**Example:**

```json
// Request
{"mcp_server": "math"}

// Response
{
  "mcp_server": "math", "state": "ready", "predefined": false,
  "tools": [
    {"name": "add", "description": "Add two numbers",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}}}
  ]
}
```

Errors: `unknown_mcp_server: <id>` (`error_type: ValueError`)

### `hangar_details` {#hangar_details}

Detailed information about a MCP server or group, including health tracking, idle time, and tool access policy.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server ID or Group ID |

**Side Effects:** None (read-only).

**Returns:**

For a MCP server:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_server_id` | `str` | MCP Server ID |
| `state` | `str` | Current state |
| `mode` | `str` | MCP Server mode |
| `provenance` | `str` | How the server was registered: `human` (configuration, REST API or CLI) or `discovery` (a discovery source) |
| `alive` | `bool` | Whether the MCP server process is running |
| `tools` | `list[object]` | Tool list with schemas, filtered by the tool access policy |
| `withheld_tools` | `list[object]` | Present only when a tool is withheld: each tool left out of `tools` and `hangar_tools` because it drifted from a pin under `digest_enforcement: block`, with `name`, `reason` (`digest_drift`), `digest` and `pinned_digest`, and never its description. Re-pinning (`mcp-hangar pin --write`) returns it |
| `health` | `object` | Health tracking: `consecutive_failures`, `total_invocations`, `total_failures`, `success_rate`, `can_retry`, `last_success_ago` and `last_failure_ago` (seconds, or `null`) |
| `idle_time` | `float \| None` | Seconds since last use |
| `meta` | `object` | MCP Server metadata, such as `init_result`, `tools_count` and `started_at` |
| `dead` | `object \| None` | `null` unless `state` is `dead`; then `reason`, `since`, `retry_allowed_at`, `revived_by` |
| `tools_policy` | `object` | Tool access policy: `active` and `unrestricted`; with a policy configured also `has_allow_list` and `has_deny_list`; and `filtered_count` when the policy hid tools from `tools` |

For a group:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `group_id` | `str` | Group ID |
| `description` | `str \| None` | Group description |
| `state` | `str` | Group availability state: `inactive`, `partial`, `healthy` or `degraded` (circuit open). Not a server lifecycle state |
| `strategy` | `str` | Load balancing strategy |
| `min_healthy` | `int` | Minimum healthy members |
| `healthy_count` | `int` | Members that are `ready` and in rotation |
| `members_in_rotation_count` | `int` | Members in rotation, in any state |
| `total_members` | `int` | Total member count |
| `is_available` | `bool` | Whether the group can accept requests |
| `circuit_open` | `bool` | Whether the circuit breaker is open |
| `members` | `list[object]` | Members with `id`, `state`, `in_rotation`, `vacant`, `weight`, `priority`, `consecutive_failures`. See [vacant members](#hangar_group_list) |

**Example:**

```json
// Request
{"mcp_server": "math"}

// Response
{
  "mcp_server_id": "math", "state": "ready", "mode": "subprocess", "provenance": "human", "alive": true,
  "tools": [{"name": "add", "description": "Add two numbers", "inputSchema": {...}}],
  "health": {"consecutive_failures": 0, "total_invocations": 2, "total_failures": 0, "success_rate": 1.0,
             "can_retry": true, "last_success_ago": 16.0, "last_failure_ago": null},
  "idle_time": 45.2,
  "meta": {"tools_count": 4, "started_at": 1791133207.8, "init_result": {...}},
  "dead": null,
  "tools_policy": {"active": false, "unrestricted": true}
}
```

Errors: `unknown_mcp_server: <id>` (`error_type: ValueError`)

### `hangar_warm` {#hangar_warm}

Pre-start one or more MCP servers so the first tool call does not incur cold-start latency. Groups are skipped. Warming all MCP servers skips `dead` ones and lists them in `skipped_dead`; name a dead server to start it.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_servers` | `str \| None` | `None` | Comma-separated MCP server IDs. `None` warms all MCP servers. |

**Side Effects:** Starts specified MCP server processes.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `warmed` | `list[str]` | Successfully warmed MCP server IDs |
| `already_warm` | `list[str]` | MCP servers that were already running |
| `skipped_dead` | `list[str]` | Dead MCP servers left alone because no names were given |
| `failed` | `list[object]` | Failed MCP servers with `id` and `error`; an unknown name fails with `McpServer not found` |
| `summary` | `str` | Human-readable summary |

**Example:**

```json
// Request
{"mcp_servers": "math,filesystem"}

// Response
{
  "warmed": ["math"], "already_warm": ["filesystem"], "skipped_dead": [], "failed": [],
  "summary": "Warmed 1 mcp_servers, 1 already warm, 0 failed"
}
```

## Health

### `hangar_health` {#hangar_health}

Health summary of the replica that answers the call: MCP server state counts and security information.

**Scope: replica-local.** This works the same way as [`hangar_status`](#hangar_status). The answer describes the replica named in `replica.instance_id`, not the fleet. It is read from the same snapshot as `hangar_status`, so from one replica the two tools agree.

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `status` | `str` | Overall status. `degraded` while a compliance file export is failing |
| `mcp_servers` | `object` | `total` and `by_state` breakdown (`cold`, `ready`, `degraded`, `dead`), counting configured and hot-loaded servers on this replica |
| `groups` | `object` | `total`, `by_state`, `total_members`, `healthy_members`, `members_in_rotation_count` |
| `security` | `object` | Rate limiting info: `rate_limiting.active_buckets`, and `rate_limiting.config` with `requests_per_second`, `burst_size`, `scope` |
| `replica` | `object` | The replica that answered: `instance_id`, `uptime_seconds`, `uptime` |
| `scope` | `str` | Always `"replica"` |
| `scope_note` | `str` | The same scope, stated in words |
| `catalogue` | `object` | Present only on `front_door` with `tool_access.required_catalogue` in force: `complete`, `holds_readiness`, `required`, `missing`, `not_retried` (each unprojected server the retry will not start, with its dead reason) and `retry`. `/health/ready` reports the catalogue without the ids |
| `compliance_export` | `object` | *(2.25.0)* Present only when `MCP_COMPLIANCE_OUTPUT` sends the compliance (SIEM) export to a file: `status` (`healthy`, or `degraded` from a failed write until one succeeds), `format`, `failures` since boot, `last_reason`, and the file path as `output`. `/health/ready` carries the same object without `output` and stays `200`. See [Compliance](../operations/COMPLIANCE.md) |

**Example:**

```json
// Request
{}

// Response
{
  "status": "healthy",
  "mcp_servers": {"total": 3, "by_state": {"ready": 2, "cold": 1}},
  "groups": {"total": 1, "by_state": {"healthy": 1}, "total_members": 3, "healthy_members": 3,
             "members_in_rotation_count": 3},
  "security": {"rate_limiting": {"active_buckets": 0,
                                 "config": {"requests_per_second": 10.0, "burst_size": 20, "scope": "global"}}},
  "replica": {"instance_id": "hangar-0-3fa81c2e", "uptime_seconds": 8100.0, "uptime": "2h 15m"},
  "scope": "replica",
  "scope_note": "This describes what the replica named in replica.instance_id knows, not the fleet. ..."
}
```

`groups.healthy_members` sums the groups' `healthy_count`: members that are `ready` and in rotation. `groups.members_in_rotation_count` sums the members in rotation, in any state.

### `hangar_metrics` {#hangar_metrics}

MCP Server metrics in JSON or Prometheus exposition format.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `format` | `str` | `"json"` | Output format: `"json"` or `"prometheus"`. Any other value returns JSON |

**Side Effects:** None (read-only).

**Returns (JSON format):**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_servers` | `dict[str, object]` | Per-MCP server metrics: `state`, `mode`, `tools_count`, `invocations`, `errors`, `avg_latency_ms` |
| `groups` | `dict[str, object]` | Per-group metrics: `state`, `strategy`, `total_members`, `healthy_members` (members `ready` and in rotation), `members_in_rotation_count` |
| `tool_calls` | `dict[str, object]` | Per-tool metrics keyed by `<mcp_server>.<tool>`: `count`, `errors` |
| `discovery` | `object` | Discovery metrics per source type: `mcp_servers_discovered`, `mcp_servers_registered`, `mcp_servers_quarantined`, `cycles` |
| `errors` | `dict[str, int]` | Error counts keyed by the `error_type` label, which for an upstream JSON-RPC error is its code, such as `"-1"` |
| `performance` | `object` | Performance metrics |
| `summary` | `object` | Totals: `total_mcp_servers`, `total_groups`, `total_tool_calls`, `total_errors` |

When `format` is `"prometheus"`, the response contains a single `metrics` field with Prometheus exposition text.

**Example:**

```json
// Request
{"format": "json"}

// Response
{
  "mcp_servers": {"math": {"state": "ready", "mode": "subprocess", "tools_count": 4,
                          "invocations": 150, "errors": 2, "avg_latency_ms": 12.3}},
  "groups": {},
  "tool_calls": {"math.add": {"count": 100, "errors": 0}},
  "summary": {"total_mcp_servers": 1, "total_groups": 0, "total_tool_calls": 150, "total_errors": 2}
}
```

## Discovery

### `hangar_discover` (async) {#hangar_discover}

Trigger a discovery scan across all enabled sources. Discovered MCP servers are added to the pending list for approval (unless `auto_register` is enabled).

**Parameters:** None.

**Side Effects:** Scans all enabled discovery sources. Updates the pending MCP server list.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `discovered_count` | `int` | Total MCP servers discovered |
| `registered_count` | `int` | MCP servers auto-registered |
| `updated_count` | `int` | Existing MCP servers updated |
| `deregistered_count` | `int` | MCP servers deregistered (authoritative mode) |
| `quarantined_count` | `int` | MCP servers quarantined |
| `error_count` | `int` | Discovery errors |
| `duration_ms` | `float` | Scan duration in milliseconds |
| `source_results` | `dict[str, int]` | Discovered count per source type |

Returns `{error: "Discovery not configured. Enable discovery in config.yaml"}` when discovery is not enabled.

In a cluster that shares a management lease, a scan is refused with an error on an instance that does not hold the lease: discovery runs only on the instance that does, so send it there. A standalone gateway always holds the lease. *Since 2.34.4.*

**Example:**

```json
// Request
{}

// Response
{
  "discovered_count": 5, "registered_count": 3, "updated_count": 1,
  "deregistered_count": 0, "quarantined_count": 1, "error_count": 0,
  "duration_ms": 1250.0, "source_results": {"docker": 3, "filesystem": 2}
}
```

### `hangar_discovered` {#hangar_discovered}

List MCP servers discovered but not yet registered (pending approval).

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `pending` | `list[object]` | Pending MCP servers with `name`, `source`, `mode`, `discovered_at`, `fingerprint`, `definition_digest` |

`definition_digest` is the full SHA-256 of the definition (its connection, metadata, mode and source), the value [`hangar_approve`](#hangar_approve) binds an approval to. `fingerprint` is 16 characters, kept for change detection, and does not bind. *Since 2.34.4.*

A pending entry is cleared once a scan no longer reports that definition: the source reports the running definition again or another one under the name, or a source that is healthy after the scan stops reporting the name. A definition still reported next to another under the same name is kept.

Returns `{error: ...}` when discovery is not configured.

**Example:**

```json
// Request
{}

// Response
{
  "pending": [
    {"name": "new-api", "source": "docker", "mode": "remote",
     "discovered_at": "2026-01-15T10:30:00Z", "fingerprint": "abc123",
     "definition_digest": "9f86d0...0a08"}
  ]
}
```

### `hangar_quarantine` {#hangar_quarantine}

List MCP servers that failed health checks during discovery and were quarantined.

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `quarantined` | `list[object]` | Quarantined MCP servers with `name`, `source`, `reason`, `quarantine_time`, `fingerprint`, `definition_digest` |

Returns `{error: ...}` when discovery is not configured.

**Example:**

```json
// Request
{}

// Response
{
  "quarantined": [
    {"name": "broken-api", "source": "docker", "reason": "health_check_failed",
     "quarantine_time": "2026-01-15T10:30:00Z", "fingerprint": "abc123",
     "definition_digest": "9f86d0...0a08"}
  ]
}
```

### `hangar_approve` (async) {#hangar_approve}

Approve a pending or quarantined MCP server for registration, or a changed definition of a running discovered server.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server` | `str` | required | MCP Server name from `hangar_discovered` or `hangar_quarantine` output |
| `definition_digest` | `str \| None` | `None` | The `definition_digest` of the definition you reviewed, from the same listing: 64 lowercase hex characters, not the 16-character `fingerprint`. Given, the approval applies only that definition. A value that is not such a digest is an invalid argument; `null` is the same as leaving it out |

**Side Effects:** Registers the MCP server in COLD state, or replaces the running definition with the approved change, after its calls in flight finish. Removes it from the pending or quarantine list. A refused approval changes nothing: the definition keeps waiting where it waited, with the same `definition_digest`, and a running server is untouched.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `approved` | `bool` | Whether approval succeeded |
| `mcp_server` | `str` | MCP Server name |
| `status` | `str` | `"registered"` for a new server, `"updated"` for an applied change of a running one |
| `error` | `str` | Error message on failure |

**Binding to what you reviewed.** A source re-reports its definition every cycle, so the one waiting under a name can change between listing and approving it. With `definition_digest`, an approval whose definition now has another digest is refused with the tool error `DiscoveredDefinitionChangedError`, whose message names the current digest, and nothing changes: review it again and approve that digest. Without `definition_digest`, whatever waits under the name is applied, as before, and `discovery_approval_not_bound` is logged at WARNING. *Since 2.34.4.*

**Refusals.** Each answers `{"approved": false, "mcp_server": "...", "error": "approval refused: <reason>"}` and leaves the definition waiting:

- The definition fails the checks an automatic registration runs: the input validator on its command, or its source's own policy (a Kubernetes namespace the source may not take from, for example). So does one whose source is no longer registered. Approval still overrides the other reasons a definition is quarantined: a failed health or schema check, and the rate and count limits. *Since 2.34.4.*
- The control plane refuses the registration, for instance because a server of that name already exists. *Since 2.34.5*; before, it answered `approved: true, status: registered` and dropped the entry.
- The replacement of a running server's changed definition is refused or fails. *Since 2.34.5*; before, it answered with a bare error and the change was gone from the listings until the next discovery cycle parked it again.

A name in neither list answers `{"approved": false, ..., "error": "McpServer not found in quarantine or pending"}`.

**Ordering and the lease.** An approval and a discovery cycle on the same server take turns: an approval that arrives mid-cycle waits for the cycle to finish and then sees what it left, so an approval bound to a digest the cycle has since replaced is refused as above. Approvals and cycles on different servers do not wait for each other. In a cluster that shares a management lease, an approval is refused with an error on an instance that does not hold the lease; send it to the instance that does. *Since 2.34.4.*

Returns `{error: ...}` when discovery is not configured.

**Example:**

```json
// Request
{"mcp_server": "new-api", "definition_digest": "9f86d0...0a08"}

// Response
{"approved": true, "mcp_server": "new-api", "status": "registered"}
```

### `hangar_sources` (async) {#hangar_sources}

List the status of all configured discovery sources.

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `sources` | `list[object]` | Sources with `id`, `source_type`, `mode`, `is_healthy`, `is_enabled`, `last_discovery`, `mcp_servers_count`, `error_message` |

`id` is the id the per-source REST routes take -- `PUT` and `DELETE
/api/discovery/sources/{source_id}`, plus its `/scan` and `/enable` sub-routes.
The collection routes, `GET` and `POST /api/discovery/sources`, take no id at
all. A source declared in `config.yaml` derives its id from the source type
rather than generating one, so it is the same id after a restart.

This tool returns the raw source status; the REST listing is filtered. `GET
/api/discovery/sources` strips the id of any source the discovery registry no
longer knows, so an id listed there is always one the per-source routes accept.
`hangar_sources` does not: after a `DELETE` of a source the orchestrator keeps
running, it can still report that source's id, and the routes answer 404 for it.
Script against the tool accordingly. *Since 2.5.0.*

Returns `{error: ...}` when discovery is not configured.

**Example:**

```json
// Request
{}

// Response
{
  "sources": [
    {"id": "28018ad1-4d9d-54dc-9e4e-c5d856af4612",
     "source_type": "docker", "mode": "additive", "is_healthy": true,
     "is_enabled": true, "last_discovery": "2026-01-15T10:30:00Z",
     "mcp_servers_count": 3, "error_message": null}
  ]
}
```

## Groups

### `hangar_group_list` {#hangar_group_list}

List all MCP server groups with member details, health state, and load balancing configuration.

**Parameters:** None.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `groups` | `list[object]` | Groups with `group_id`, `description`, `state`, `strategy`, `min_healthy`, `healthy_count`, `members_in_rotation_count`, `total_members`, `is_available`, `circuit_open`, `members` |

Each member in the `members` list contains: `id`, `state`, `in_rotation`, `vacant`, `weight`, `priority`, `consecutive_failures`.

**Vacant members.** *Since 2.34.4* a server deleted while it is a group member (`DELETE /api/mcp_servers/{id}`, or a discovery source removing it after its TTL) stays in the group as a vacant member: `"vacant": true`, `"state": "cold"` and `"in_rotation": false`. No call, rebalance, start or recovery probe reaches it. It still counts in `total_members` and no longer counts as in rotation, so a group whose only member is deleted reads `inactive` and refuses calls. A server that discovery registers again under the same id fills the member, with the weight, priority and rotation it had. A server re-created over the API leaves it vacant: re-add it with `POST /api/groups/{id}/members`, or remove the member with `DELETE /api/groups/{id}/members/{member_id}`. Before 2.34.4 the group kept the deleted server's stopped copy in rotation and the next call through the group started it again, outside the fleet.

**Example:**

```json
// Request
{}

// Response
{
  "groups": [
    {
      "group_id": "llm-group", "description": "LLM pool", "state": "healthy",
      "strategy": "round_robin", "min_healthy": 1, "healthy_count": 2,
      "members_in_rotation_count": 2, "total_members": 2, "is_available": true,
      "circuit_open": false,
      "members": [
        {"id": "llm-1", "state": "ready", "in_rotation": true, "vacant": false,
         "weight": 50, "priority": 1, "consecutive_failures": 0},
        {"id": "llm-2", "state": "ready", "in_rotation": true, "vacant": false,
         "weight": 50, "priority": 2, "consecutive_failures": 0}
      ]
    }
  ]
}
```

### `hangar_group_rebalance` {#hangar_group_rebalance}

Rebalance a group by re-checking all members. Recovered members rejoin rotation, failed members are removed. Resets the circuit breaker.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `group` | `str` | required | Group ID |

**Side Effects:** Re-checks all members. Updates rotation membership. Resets circuit breaker.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `group_id` | `str` | Group ID |
| `state` | `str` | Group state after rebalance |
| `healthy_count` | `int` | Members that are `ready` and in rotation |
| `members_in_rotation_count` | `int` | Members in rotation, in any state |
| `total_members` | `int` | Total member count |
| `members_in_rotation` | `list[str]` | Member IDs currently in rotation |

**Example:**

```json
// Request
{"group": "llm-group"}

// Response
{
  "group_id": "llm-group", "state": "healthy", "healthy_count": 2,
  "members_in_rotation_count": 2, "total_members": 2, "members_in_rotation": ["llm-1", "llm-2"]
}
```

Errors: `unknown_group: <id>` (`error_type: ValueError`), also for the ID of a server that is not a group.

## Batch and Continuation

### `hangar_call` {#hangar_call}

Invoke tools on MCP servers. Supports single calls and parallel batch execution with two-level concurrency control (per-batch and system-wide).

**Parameters:**

| Parameter | Type | Default | Range | Description |
| ----------- | ------ | --------- | ------- | ------------- |
| `calls` | `list[object]` | required | 0--100 items | List of `{mcp_server, tool, arguments, timeout?}` objects. `mcp_server` is a server or group ID; `arguments` is required, `{}` for none; a per-call `timeout` must be a positive number |
| `max_concurrency` | `int` | `10` | 1--50 | Parallel workers for this batch |
| `timeout` | `float` | `60` | 1--300 | Batch timeout in seconds |
| `fail_fast` | `bool` | `false` | -- | Stop batch on first error |
| `max_attempts` | `int \| None` | `None` | 1--10 | Total attempts per call including retries. See below |

A value outside its range is clamped to the nearest bound, not rejected: `max_concurrency: 51` runs with 50. An empty `calls` list returns a successful batch with `total: 0`. More than 100 calls is a validation error.

**`max_attempts`.** Omitted (`null`), each call retries under the gateway's configured `retry:` policy, and runs
once when none is configured. An explicit `1` is exactly one attempt, whatever is configured: a caller whose tool
is not idempotent can say so. With a `retry:` policy configured, `2`--`10` can only lower its attempt count, never
raise it; with none, `2`--`10` retries up to that many attempts. Before 2.29.0 the default was `1` and an explicit
`1` still got the configured retries.

**Side Effects:** May start cold MCP servers. Executes tool calls on MCP servers.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `batch_id` | `str` | Unique batch identifier |
| `success` | `bool` | `true` if all calls succeeded |
| `total` | `int` | Total calls in batch |
| `succeeded` | `int` | Successful call count |
| `failed` | `int` | Failed call count |
| `elapsed_ms` | `float` | Total batch execution time |
| `results` | `list[object]` | Per-call results with `index`, `call_id`, `success`, `result`, `error`, `error_type`, `elapsed_ms`. `result` is the upstream's `tools/call` result as it returned it, typically `{"content": [...]}` |

On validation failure -- an unknown server, a missing `arguments`, more than 100 calls -- nothing runs and the response is `{batch_id, success: false, error: "Validation failed", validation_errors}`, where `validation_errors` is a list of `{index, field, message}`, for example `{"index": 0, "field": "mcp_server", "message": "McpServer 'unknown' not found"}`.

A tool name is checked at validation only on a server whose tool list is already known: one that has started, or
that declares its tools in the configuration. There, an unknown tool is the validation error
`Tool '<tool>' not found in mcp_server '<id>'`. On a group, or a cold server with no declared tools, the batch runs
and that call alone fails with `error_type: "ToolNotFoundError"` and `error` `Tool not found: <tool>`.

A call the caller may not make fails on its own, with `error_type: "AuthorizationDenied"` and `error` `Not authorized to invoke tool '<tool>': tool:invoke permission required`; the rest of the batch runs. A tool error the upstream reports, as a JSON-RPC error or an `isError` result, has `error_type: "ToolInvocationError"` and an `error` starting `tool_error:`.

With truncation enabled, a result over the batch's size budget is cut and carries `truncated: true`, `truncated_reason` (for example `batch_budget_exceeded`), `original_size_bytes` and a `continuation_id` -- use `hangar_fetch_continuation` to retrieve the full data.

When a call runs under a retry policy (a configured `retry:` block, or `max_attempts` above 1), its result carries `retry_metadata`: `attempts` (a count), `retries` (a list, one entry per retry) and `total_time_ms`.

**Example:**

```json
// Request
{
  "calls": [
    {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}},
    {"mcp_server": "math", "tool": "multiply", "arguments": {"a": 3, "b": 4}}
  ],
  "max_concurrency": 5
}

// Response
{
  "batch_id": "batch-abc123", "success": true, "total": 2,
  "succeeded": 2, "failed": 0, "elapsed_ms": 45.2,
  "results": [
    {"index": 0, "call_id": "call-1", "success": true,
     "result": {"content": [{"type": "text", "text": "3"}]},
     "error": null, "error_type": null, "elapsed_ms": 20.1},
    {"index": 1, "call_id": "call-2", "success": true,
     "result": {"content": [{"type": "text", "text": "12"}]},
     "error": null, "error_type": null, "elapsed_ms": 22.8}
  ]
}
```

### `hangar_fetch_continuation` {#hangar_fetch_continuation}

Fetch full data for a truncated batch response. Continuation IDs are returned when individual call results exceed the response size limit.

**Parameters:**

| Parameter | Type | Default | Range | Description |
| ----------- | ------ | --------- | ------- | ------------- |
| `continuation_id` | `str` | required | starts with `"cont_"` | Continuation ID from a truncated result |
| `offset` | `int` | `0` | >= 0 | Byte offset to start reading from |
| `limit` | `int` | `500000` | 1--2000000 | Maximum bytes to return. `0` or less uses the default; more than 2000000 is clamped to it |

**Side Effects:** None (read-only cache access).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `found` | `bool` | Whether the continuation data exists |
| `data` | `any` | The continuation data (when found): the original value when this read returns all of it, a string slice of its JSON when it does not |
| `total_size_bytes` | `int` | Total size of the cached data |
| `offset` | `int` | Current read offset |
| `has_more` | `bool` | Whether more data is available |
| `complete` | `bool` | Whether all data has been returned |

Returns `{found: false, error: "Continuation not found (may have expired)"}` when the continuation ID is unknown or expired, and also to a caller other than the tenant and principal whose `hangar_call` produced it.

**Example:**

```json
// Request
{"continuation_id": "cont_abc123", "offset": 0, "limit": 500000}

// Response
{
  "found": true, "data": "...full response content...",
  "total_size_bytes": 250000, "offset": 0, "has_more": false, "complete": true
}
```

Errors (`error_type: ValueError`): `continuation_id is required`, `Invalid continuation_id format (must start with 'cont_')`, `offset must be non-negative`.

### `hangar_delete_continuation` {#hangar_delete_continuation}

Delete cached continuation data to free memory.

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `continuation_id` | `str` | required | Continuation ID to delete |

**Side Effects:** Removes the cached response from memory.

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `deleted` | `bool` | Whether the data was found and deleted |
| `continuation_id` | `str` | The requested continuation ID |

Returns `{deleted: false, continuation_id: "..."}` when the ID is not found. Returns `{deleted: false, continuation_id: "...", error: "..."}` when the truncation cache is unavailable.

**Example:**

```json
// Request
{"continuation_id": "cont_abc123"}

// Response
{"deleted": true, "continuation_id": "cont_abc123"}
```

Errors: `continuation_id is required` (`error_type: ValueError`) if `continuation_id` is empty. Like a fetch, a delete reaches only the caller's own continuations.

## Identity

### `hangar_whoami` {#hangar_whoami}

Show who the gateway thinks the caller is: the principal, tenant, groups and the role bindings the authorizer
decides it on. Use it when a call was refused and you need to know which identity and which roles it was judged by.
It reads only the caller's own identity; there is no way to ask about another principal or tenant.

**Parameters:** None.

**Permission:** None, but the call needs an authenticated caller. With authentication off, or for an anonymous
caller, there is no identity to report, and the call is refused with `isError: true` and the text
`Error executing tool hangar_whoami: 'hangar_whoami' answers only an authenticated caller`. Over stdio, a declared
`auth.stdio.principal` is an identity.

**Side Effects:** None (read-only).

**Returns:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `principal` | `object` | `id` and `type` |
| `tenant_id` | `str \| None` | The caller's tenant |
| `groups` | `list[str]` | The caller's groups, sorted |
| `roles` | `list[object]` | Each binding as `{role, scope}`, where `scope` is `global` or `tenant:<id>`. A role bound at `tenant:<id>` grants only within that tenant, so it does not admit a management tool, which acts on the whole fleet |
| `opa_policy` | `str \| None` | `null`, or `may_admit_more` / `may_refuse_more` when an OPA policy can change what those roles decide |

**Example:**

```json
// Request
{}

// Response
{
  "principal": {"id": "local-user", "type": "user"},
  "tenant_id": "local",
  "groups": [],
  "roles": [{"role": "viewer", "scope": "global"}],
  "opa_policy": null
}
```
