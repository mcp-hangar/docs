# 02 — Health Checks

> **Prerequisite:** [01 — HTTP Gateway](01-http-gateway.md)
> **You will need:** Working setup from recipe 01, ability to kill the test MCP server
> **Time:** 10 minutes
> **Adds:** Automatic health monitoring with state transitions on failure

## The Problem

Your MCP server from recipe 01 crashes at 3 AM. Hangar doesn't know. It keeps sending requests to a dead endpoint and forwards cryptic connection errors back to Claude. Claude retries. More errors. The on-call engineer gets paged because "AI is broken" — but nobody knows which MCP server is down until someone checks logs. Hangar could have told you within three minutes.

## The Config

```yaml
# config.yaml — Recipe 02: Health Checks

mcp_servers:
  my-mcp:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "My remote MCP server"
    health_check_interval_s: 30            # NEW: added in this recipe
    max_consecutive_failures: 3            # NEW: added in this recipe
    http:
      connect_timeout: 10.0
      read_timeout: 30.0
```

Save this as `~/.config/mcp-hangar/config.yaml` (or update your existing file).

## Try It

1. Start Hangar in the background, in HTTP mode

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 127.0.0.1 --port 8000 --log-file /tmp/hangar.log &
   sleep 5
   grep '"task": "health_check"' /tmp/hangar.log
   ```

   ```
   {"task": "health_check", "interval_s": 60, "event": "background_worker_started", "level": "info", ...}
   ```

   HTTP mode, because this Hangar has to outlive one command. A stdio Hangar
   reads its requests from stdin: started with `&`, it reads end-of-file at
   once and exits. Every step below talks to this one process, and the log
   file holds one JSON object per line. The health check worker starts with
   it.

2. Check initial status

   ```bash
   curl -s http://localhost:8000/api/mcp_servers/my-mcp
   ```

   ```
   {"mcp_server_id":"my-mcp","state":"cold","mode":"remote","alive":false,"tools":[],"health":{"consecutive_failures":0,...},...}
   ```

3. Trigger MCP server start

   ```bash
   curl -s -X POST http://localhost:8000/api/mcp_servers/my-mcp/start
   grep McpServerStateChanged /tmp/hangar.log
   ```

   ```
   {"mcp_server":"my-mcp","state":"ready","tools":["add","subtract","multiply","divide","power"]}
   {"event_type": "McpServerStateChanged", "event_id": "...", "mcp_server_id": "my-mcp", "event": "domain_event", ...}
   {"event_type": "McpServerStateChanged", "event_id": "...", "mcp_server_id": "my-mcp", "event": "domain_event", ...}
   ```

   State changes are logged as domain events, not under a name of their own:
   the event handler emits `domain_event` with the class in `event_type`. The
   line does not carry the old and new state (cold to initializing, then
   initializing to ready); `GET /api/mcp_servers/my-mcp` shows where it is.

   MCP Server transitioned to READY. Health checks now active.

4. Simulate MCP server failure

   Freeze the test server, so it still accepts connections but never answers
   -- a hung server:

   ```bash
   docker pause mcp-math
   ```

5. Wait for three health check cycles (about three minutes)

   ```bash
   echo "Waiting for health checks to detect failure..."
   sleep 200
   grep -E 'health_check_failed|degraded_by_health_check' /tmp/hangar.log
   ```

   ```
   {"event": "health_check_failed: my-mcp, error_type=TimeoutError", "level": "warning", ...}
   {"event": "health_check_failed: my-mcp, error_type=TimeoutError", "level": "warning", ...}
   {"event": "health_check_failed: my-mcp, error_type=TimeoutError", "level": "warning", ...}
   {"event": "mcp_server_degraded_by_health_check: my-mcp", "level": "warning", ...}
   ```

   One check a minute, each waiting 5 seconds for a reply; the third failure
   degrades the server.

   A stopped server (`docker stop mcp-math`) is not detected this way on
   2.24.0: the refused connection escapes the check instead of counting as a
   failure, so the log shows `background_task_failed` with
   `connection_failed: [Errno 61] Connection refused` (`Errno 111` on Linux) once a minute and the
   server stays `ready`. A tool call to it still fails, and in a group those
   failures take it out of rotation (recipe 03).

6. Verify DEGRADED state

   ```bash
   curl -s http://localhost:8000/api/mcp_servers/my-mcp
   grep -E 'McpServerDegraded|scheduling retry' /tmp/hangar.log
   ```

   ```
   {"mcp_server_id":"my-mcp","state":"degraded",...}
   {"event_type": "McpServerDegraded", ..., "mcp_server_id": "my-mcp", "event": "domain_event", ...}
   {"event": "ALERT [CRITICAL] McpServer degraded after 3 failures mcp_server=my-mcp event=McpServerDegraded", ...}
   {"event": "McpServer my-mcp degraded, scheduling retry 1/3 in 5.0s", ...}
   ```

   The state reads `initializing` instead while one of those retries is
   waiting on the frozen server.

7. MCP Server will auto-recover if restarted

   ```bash
   docker unpause mcp-math
   sleep 60
   grep 'recovered successfully' /tmp/hangar.log
   ```

   ```
   {"event": "McpServer my-mcp recovered successfully after 1 retries", ...}
   ```

   Hangar retries the start on a backoff, and the first retry after the server
   answers again brings it back to READY. If every retry fails first, the
   server is DEAD (`[DEAD]` in `hangar_status`), and only a deliberate start
   -- `POST /api/mcp_servers/my-mcp/start` or `hangar_start` -- revives it.

8. Stop Hangar

   ```bash
   kill %1
   ```

   Not `pkill -f mcp-hangar`: that also ends every other Hangar on the
   machine, Claude Desktop's included.

## What Just Happened

Hangar's background health check worker probes each READY MCP server every 60 seconds. The probe mechanism sends a `tools/list` JSON-RPC request to the MCP server with a 5-second timeout. If the MCP server responds successfully, the health check passes and `consecutive_failures` resets to 0.

When the MCP server fails to respond, Hangar records a failure in the `HealthTracker`. After `max_consecutive_failures` (3 by default) failed checks, the MCP server state transitions from READY to DEGRADED. This transition emits a `McpServerDegraded` domain event, which updates metrics and triggers alerts.

A degraded server's health check no longer probes it. Instead Hangar retries its start on a backoff (3 retries by default), and when the MCP server is back online one of them reinitializes it (DEGRADED -> INITIALIZING -> READY). No manual intervention required -- Hangar detected the failure and recovery without human involvement. Only when every retry fails does the server end up DEAD and wait for a deliberate start.

State machine transitions:

- READY -> DEGRADED (after 3 consecutive failures)
- DEGRADED -> INITIALIZING -> READY (on reinitialize after recovery)

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `health_check_interval_s` | int | `60` | Recorded on the server and reported by the API. It does **not** set the probe cadence: the background worker checks on its own interval, adjusted per state by the health tracker (skipped while cold or initializing, backed off once degraded). Treat it as documentation of intent until the scheduler reads it ([mcp-hangar#1686](https://github.com/mcp-hangar/mcp-hangar/issues/1686)) |
| `max_consecutive_failures` | int | `3` | Failures before state transition to DEGRADED |

## What's Next

Your MCP server is monitored — but when it starts failing intermittently, every request during the 60-second health check interval still hits a broken server. You need automatic protection that trips immediately on the first failure, not after 3 health checks.

→ [03 — Circuit Breaker](03-circuit-breaker.md)
