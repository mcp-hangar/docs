# 04 — Failover

> **Prerequisite:** [03 — Circuit Breaker](03-circuit-breaker.md)
> **You will need:** Two running MCP servers (primary + backup)
> **Time:** 15 minutes
> **Adds:** Automatic failover to backup MCP server with priority-based routing

## The Problem

Recipe 03 took the failing server out of rotation and saved you from waiting out a timeout on every call. But the agent still got nothing. Zero results. Requests were refused fast, and your agent couldn't complete its task. Protection is great, but errors are still errors.

Your single MCP server is one crash away from downtime. What if there was a second MCP server ready to answer while the primary recovers?

## Prerequisites

You need TWO running MCP servers. Use the in-repo test server on different
ports:

```bash
# Build the test MCP server (skip if already built in recipe 01)
docker build -t mcp-math:latest examples/provider_math/

# The recipe 01-03 container holds port 8080; remove it first
docker rm -f mcp-math

# Terminal 1: Primary server on port 8080
# Both upstreams serve streamable-http on 8080. On an image built before
# 2.5.0, add `-e MCP_TRANSPORT=streamable-http` to each -- the older default
# was stdio, so neither container bound its port and there was nothing to fail
# over between.
docker run -d --name mcp-primary -p 8080:8080 mcp-math:latest

# Terminal 2: Backup server on port 8081
docker run -d --name mcp-backup -p 8081:8080 -e MCP_PORT=8080 mcp-math:latest
```

Keep both containers running.

## The Config

```yaml
# config.yaml — Recipe 04: Failover

mcp_servers:
  my-mcp:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "Primary MCP server"
    health_check_interval_s: 30
    max_consecutive_failures: 3
    http:
      connect_timeout: 10.0
      read_timeout: 30.0

  my-mcp-backup:                           # NEW: added in this recipe
    mode: remote                           # NEW: added in this recipe
    endpoint: http://localhost:8081/mcp    # NEW: added in this recipe
    description: "Backup MCP server"       # NEW: added in this recipe
    health_check_interval_s: 30            # NEW: added in this recipe
    max_consecutive_failures: 3            # NEW: added in this recipe
    http:                                  # NEW: added in this recipe
      connect_timeout: 10.0                # NEW: added in this recipe
      read_timeout: 30.0                   # NEW: added in this recipe

  my-mcp-group:
    mode: group
    description: "Primary/backup MCP failover"
    strategy: priority                     # NEW: changed from round_robin
    min_healthy: 1
    circuit_breaker:
      failure_threshold: 3
    members:
      - id: my-mcp                         # NEW: added priority
        priority: 1                        # NEW: added priority (primary)
      - id: my-mcp-backup                  # NEW: added backup member
        priority: 2                        # NEW: backup has lower priority
```

Save this as `~/.config/mcp-hangar/config.yaml` (or update your existing file).

## Try It

1. Restart the background Hangar on the new config

   ```bash
   kill %1    # the Hangar from recipe 03, if it still runs
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 127.0.0.1 --port 8000 --log-file /tmp/hangar-failover.log &
   sleep 5
   grep -E 'group_loaded|Added member' /tmp/hangar-failover.log
   ```

   ```
   {"event": "Added member my-mcp to group my-mcp-group (weight=1, priority=1)", ...}
   {"event": "Added member my-mcp-backup to group my-mcp-group (weight=1, priority=2)", ...}
   {"group_id": "my-mcp-group", "member_count": 2, "strategy": "priority", "event": "group_loaded", ...}
   ```

2. Check group status - both members healthy

   ```bash
   /tmp/hangar-call.sh hangar_group_list | grep -E '"id"|"state"|in_rotation'
   ```

   ```
         "state": "healthy",
         "members_in_rotation_count": 2,
             "id": "my-mcp",
             "state": "ready",
             "in_rotation": true,
             "id": "my-mcp-backup",
             "state": "ready",
             "in_rotation": true,
   ```

   Both MCP servers in rotation; the group started them when it loaded.
   Primary (priority 1) will handle requests.

3. Call a tool through the group - succeeds via primary

   ```bash
   /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"success"' | head -1
   curl -s http://localhost:8000/metrics | grep '^mcp_hangar_tool_calls_total'
   ```

   ```
     "success": true,
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="success",tool="add"} 1.0
   ```

   Call succeeded. Traffic routed to primary (priority 1): each call is
   counted against the member that served it.

4. Kill the primary server

   ```bash
   docker stop mcp-primary
   ```

   Primary is now dead. Backup still running.

5. Call the same tool four times

   ```bash
   for i in 1 2 3 4; do
     /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"error"' | head -1
   done
   ```

   ```
         "error": "connection_failed: [Errno 61] Connection refused",
         "error": "connection_failed: [Errno 61] Connection refused",
         "error": null,
         "error": null,
   ```

   The first two calls still went to the primary and failed: a call is not
   retried on another member. Two failures in a row
   (`health.unhealthy_threshold`, 2 by default) took the primary out of
   rotation, and the next two calls were served by the backup.

   Since 2.25.0 health checks catch a stopped primary too: each refused
   connection counts as a failed check, and two of them take it out of
   rotation without a call having to fail first (recipe 02, step 5). On 2.24.0
   the refused connection was logged as `background_task_failed` instead, and
   only calls took the primary out. A hung primary is caught by either: calls
   that time out, or failed health checks.

6. Confirm where traffic goes now

   ```bash
   /tmp/hangar-call.sh hangar_group_list | grep -E '"id"|in_rotation|consecutive'
   curl -s http://localhost:8000/metrics | grep '^mcp_hangar_tool_calls_total'
   ```

   ```
         "members_in_rotation_count": 1,
             "id": "my-mcp",
             "in_rotation": false,
             "consecutive_failures": 2
             "id": "my-mcp-backup",
             "in_rotation": true,
             "consecutive_failures": 0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="success",tool="add"} 1.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="error",tool="add"} 2.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-backup",status="success",tool="add"} 2.0
   ```

   Same request, same result, different MCP server.

7. Restart primary and verify failback

   ```bash
   docker start mcp-primary

   echo "Waiting about three minutes for primary recovery..."
   sleep 200

   grep -E 'degraded_by_health_check|added back to rotation|recovered successfully' /tmp/hangar-failover.log
   ```

   ```
   {"event": "mcp_server_degraded_by_health_check: my-mcp", ...}
   {"event": "Member my-mcp added back to rotation", ...}
   {"event": "McpServer my-mcp recovered successfully after 1 retries", ...}
   ```

   The restarted primary does not know Hangar's MCP session any more, so the
   health checks that reach it now fail with a JSON-RPC error (`error_type=-32600`, `-32000`, ...).
   The third failure degrades it, Hangar retries the start, the retry
   reconnects with a new session, and the member is back in rotation. Primary
   recovered and back in rotation. Will reclaim traffic (priority 1 < priority 2).

   If the primary was down long enough for Hangar to give up on it, it reads `dead` (`[DEAD]` in `hangar_status`). Health checks skip a dead server and the group does not route to it, so it does not come back by itself. Call `hangar_start` on `my-mcp`, and it rejoins rotation once the start succeeds.

## What Just Happened

You introduced **MCP server groups with priority-based routing** for automatic failover. The group contains two MCP servers: `my-mcp` (priority 1, primary) and `my-mcp-backup` (priority 2, backup).

**Priority strategy mechanics:**

The `priority` load balancing strategy always routes traffic to the lowest-numbered healthy member in rotation. Priority 1 is highest priority (primary). If priority 1 becomes unhealthy, traffic automatically fails over to priority 2 (backup). When priority 1 recovers, it reclaims traffic (failback).

**Failover flow:**

1. **Normal operation**: Primary (priority 1) handles all requests. Backup is healthy but idle.
2. **Primary fails**: Two failed calls in a row (`health.unhealthy_threshold`), or a failed health check, mark the member unhealthy. The calls that fail are not retried on the backup.
3. **Failover**: Primary removed from rotation. Group selects next lowest priority → backup (priority 2) takes over.
4. **Recovery**: A success from the primary -- a completed start, a passing health check -- adds it back to rotation.
5. **Failback**: Group selects lowest priority again → primary (priority 1) reclaims traffic.

**Layer cake architecture:**

- **Recipe 02 (Health Checks)**: Per-MCP server health monitoring detects failures
- **Recipe 03 (Circuit Breaker)**: Per-group failure tracking; a failing member leaves rotation
- **Recipe 04 (Failover)**: Inter-MCP server routing changes based on health

Both MCP servers have their own health checks; the circuit breaker belongs to the group, not to either server. The group orchestrates between them. When the primary fails, the group removes it from rotation, its failures count toward the group's circuit, and its health checks keep watching it. Multiple layers of protection working together.

**min_healthy: 1** means the group requires at least 1 healthy member to stay operational. If both fail, the group itself becomes unavailable.

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `mcp_servers.<name>.strategy` | string | `round_robin` | Routing strategy. Use `priority` for failover |
| `mcp_servers.<name>.members[].id` | string | — | MCP Server ID (must exist in `mcp_servers:` section) |
| `mcp_servers.<name>.members[].priority` | int | `1` | Routing priority (lower number = higher priority) |
| `mcp_servers.<name>.members[].weight` | int | `1` | Weight for weighted strategies (not used with priority) |

## What's Next

You have failover — one primary, one backup. But what if you have three, five, ten instances of the same MCP server? You don't want priority failover — you want to spread the load evenly across all healthy instances.

→ [05 — Load Balancing](05-load-balancing.md)
