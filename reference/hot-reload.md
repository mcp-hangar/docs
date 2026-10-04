# Hot-Reload Configuration

Reload configuration without restarting the server. Add, remove, or modify MCP servers while preserving active connections for unchanged MCP servers.

## Quick Start

```bash
# Start server, naming the file to watch
mcp-hangar serve --http --host 127.0.0.1 --port 8000 --config config.yaml

# Edit config.yaml in another terminal - changes apply automatically

# Or trigger manually
kill -HUP $(pgrep -f "mcp-hangar serve")
```

Name the file with `--config` or `MCP_CONFIG`. A gateway that picked up
`./config.yaml` on its own has no path to reload: the watcher logs
`config_reload_worker_disabled` with `reason=no_config_path`, and SIGHUP, the
tool and the REST endpoint fail with `No configuration path specified`.

## Overview

| Trigger | Latency | Use Case |
| --------- | --------- | ---------- |
| File polling | up to 5s (configurable) | Default |
| File watcher (watchdog) | ~1s | Only when the `watchdog` package is installed |
| SIGHUP signal | Immediate | Scripted deployments, CI/CD |
| MCP tool | Immediate | Interactive reload from AI assistant |
| `POST /api/config/reload` | Immediate | HTTP mode, REST API |

All reload operations are **atomic**: changes are validated before application. Invalid configuration is rejected; current config preserved.
A file that changes `tool_access.mode` is refused the same way: the mode needs a restart.

## Configuration

```yaml
# Optional: customize hot-reload behavior
config_reload:
  enabled: true       # default: true
  use_watchdog: true  # default: true; needs the watchdog package, else polling
  interval_s: 5       # polling interval when watchdog is not used
```

### Options

| Option | Type | Default | Description |
| -------- | ------ | --------- | ------------- |
| `enabled` | bool | `true` | Enable automatic file watching |
| `use_watchdog` | bool | `true` | Use watchdog library (inotify/fsevents) when it is installed |
| `interval_s` | int | `5` | Polling interval in seconds |

## Triggering Reload

### Automatic File Watching

Enabled by default. mcp-hangar does not install [watchdog](https://github.com/gorakhargosh/watchdog),
so by default the file's modification time is polled every `interval_s`. With
`pip install watchdog` and `use_watchdog: true`, file system events are used
instead, with a 1s debounce.

### SIGHUP Signal

Standard Unix reload pattern. Does not terminate the process.

```bash
# Find process
pgrep -f "mcp-hangar serve"

# Reload
kill -HUP <PID>

# One-liner
kill -HUP $(pgrep -f "mcp-hangar serve")
```

### MCP Tool

Reload from Claude Desktop or any MCP client:

```python
hangar_reload_config()                    # Graceful reload
hangar_reload_config(graceful=false)      # Immediate shutdown
```

**Response:**

```json
{
  "status": "success",
  "message": "Configuration reloaded successfully",
  "mcp_servers_added": ["new-api"],
  "mcp_servers_removed": ["deprecated-service"],
  "mcp_servers_updated": ["modified-mcp-server"],
  "mcp_servers_unchanged": ["stable-mcp-server"],
  "duration_ms": 45.2
}
```

On failure the tool answers `{"error": ..., "error_type": ..., "details": {}}`.

### REST API

In HTTP mode, `POST /api/config/reload` reloads the file the gateway was
started with. The optional JSON body takes `graceful`; a body that sends
`config_path` is rejected.

```bash
curl -X POST http://127.0.0.1:8000/api/config/reload
```

## Reload Behavior

| Scenario | Behavior | Final State |
| ---------- | ---------- | ------------- |
| **Added** | Registered but not started | `COLD` |
| **Removed** | Stopped gracefully, then removed | (deleted) |
| **Modified** | Old stopped, new registered | `COLD` |
| **Unchanged** | No action taken | Preserved |

### Compared Fields

Changes to anything a server is built from restart it, among them:

| Field | Description |
| ------- | ------------- |
| `mode` | MCP Server mode (subprocess, docker, remote) |
| `command` | Command and arguments |
| `image` | Container image |
| `endpoint` | Remote endpoint URL |
| `env` | Environment variables |
| `volumes` | Volume mounts |
| `network` | Network mode |
| `user` | User/group ID |
| `idle_ttl_s` | Idle timeout |
| `health_check_interval_s` | Health check interval |
| `max_consecutive_failures` | Failure threshold |
| `args`, `resources`, `read_only`, `build` | Container settings |
| `description`, `auth`, `tls`, `http`, `capabilities`, `max_response_bytes` | Other server settings |

A server's `tools` access block, `access`, `tool_access`, `tool_projection`
(pins) and `header_exposure`, and a group member's `weight` and `priority`, are
applied without a restart.

**Normalization:**

- Every default is applied before comparing: leaving a field out and writing
  its default value are the same
- An explicit `null`, or an empty value where the default is not empty, is a
  change: `env: null` or `resources: {}` restarts the server (`env: {}` does not)

## Examples

### Add MCP Server

**Before:**

```yaml
mcp_servers:
  math:
    mode: subprocess
    command: [python, -m, math_server]
```

**After:**

```yaml
mcp_servers:
  math:
    mode: subprocess
    command: [python, -m, math_server]

  filesystem:
    mode: subprocess
    command: [npx, -y, "@modelcontextprotocol/server-filesystem", "/home/user/documents"]
```

**Result:** `math` unchanged, `filesystem` added in `COLD` state.

### Update MCP Server

**Before:**

```yaml
mcp_servers:
  database:
    mode: remote
    endpoint: https://db-mcp.internal/v1
    idle_ttl_s: 300
```

**After:**

```yaml
mcp_servers:
  database:
    mode: remote
    endpoint: https://db-mcp.internal/v2
    idle_ttl_s: 600
    env:
      POOL_SIZE: "10"
```

**Result:** `database` stopped gracefully, new instance created.

### Remove MCP Server

**Before:**

```yaml
mcp_servers:
  legacy-api:
    mode: subprocess
    command: [python, legacy_server.py]

  modern-api:
    mode: remote
    endpoint: https://api.example.com/mcp
```

**After:**

```yaml
mcp_servers:
  modern-api:
    mode: remote
    endpoint: https://api.example.com/mcp
```

**Result:** `legacy-api` stopped and removed, `modern-api` unchanged.

### Change MCP Server Mode

**Before:**

```yaml
mcp_servers:
  search:
    mode: subprocess
    command: [python, -m, search_v1]
```

**After:**

```yaml
mcp_servers:
  search:
    mode: docker
    image: search-mcp:v2
    env:
      INDEX_PATH: /data/index
    volumes:
      - ./data:/data:ro
```

**Result:** Subprocess stopped; `search` is registered as a Docker server in `COLD` state, and its container starts on the next call.

## Events

Hot-reload emits domain events for observability:

| Event | When |
| ------- | ------ |
| `ConfigurationReloadRequested` | Before reload starts |
| `ConfigurationReloaded` | After successful reload |
| `ConfigurationReloadFailed` | On validation/apply failure |

```python
ConfigurationReloaded(
    config_path="/app/config.yaml",
    mcp_servers_added=["new-api"],
    mcp_servers_removed=["old-api"],
    mcp_servers_updated=["modified"],
    mcp_servers_unchanged=["stable"],
    reload_duration_ms=42.5,
    requested_by="file_watcher"
)
```

## Disabling Hot-Reload

```yaml
config_reload:
  enabled: false
```

> SIGHUP and MCP tool remain functional for manual reload.

## Monitoring

### Log Events

| Event | Description |
| ------- | ------------- |
| `config_reload_worker_started` | Worker initialized |
| `config_file_modified_detected` | File change detected (polling mode) |
| `reload_signal_received` | SIGHUP received |
| `triggering_config_reload` | Reload initiated |
| `configuration_reloaded` | Reload successful |
| `configuration_reload_failed` | Reload failed |

### Structured Logs

```json
{"event": "configuration_reloaded", "config_path": "config.yaml",
 "duration_ms": 42.5, "added": 1, "removed": 0, "updated": 2}
```

## Limitations

| Limitation | Workaround |
| ------------ | ------------ |
| `tool_access.mode` change refused | Restart the gateway |
| Hot-loaded MCP servers unaffected | Use `hangar_unload` to manage separately |
| Only `mcp_servers` (with groups and their policies), `tool_access.required_catalogue`, `execution`, `headers.param_validation`, `resource_links`, `interceptors` and `ui_resources` are applied | Restart the gateway for any other section (`auth`, `event_store`, `logging`, ...) |
| In-flight requests | Completed before MCP server stops (graceful mode) |

## Troubleshooting

### Reload Not Triggering

```bash
# Check watchdog installed
pip list | grep watchdog

# Check worker status (config_reload_worker_disabled reason=no_config_path:
# restart with --config or MCP_CONFIG)
grep "config_reload_worker" logs/mcp-hangar.log

# Manual reload
kill -HUP $(pgrep -f "mcp-hangar serve")
```

### Invalid Configuration

```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check mcp_servers section
grep -q "^mcp_servers:" config.yaml && echo "OK" || echo "Missing"

# Check logs
grep "configuration_reload_failed" logs/mcp-hangar.log
```

### MCP Server Not Starting

```bash
# Check mcp_server added
grep "mcp_server_added" logs/mcp-hangar.log

# Check status
hangar_status()

# Start manually
hangar_start(mcp_server="my-mcp-server")
```

## Security

| Consideration | Implementation |
| --------------- | ---------------- |
| Validation before apply | Invalid config rejected |
| Atomic operations | All-or-nothing semantics |
| Graceful shutdown | Active requests complete first |
| Audit trail | All reloads logged with source |
| File permissions | Ensure config not world-writable |
