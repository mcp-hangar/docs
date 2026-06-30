# 05 -- Load Balancing

> **Prerequisite:** [04 -- Failover](04-failover.md)
> **You will need:** Running Hangar with a MCP server group from recipe 04
> **Time:** 5 minutes
> **Adds:** Distribute requests evenly across multiple MCP server instances

## The Problem

You have two MCP servers in a failover group. All traffic goes to the primary -- the backup sits idle. You want to use both MCP servers and spread the load.

## The Config

```yaml
# config.yaml -- Recipe 05: Load Balancing
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: "http://localhost:8080/mcp"
    health_check_interval_s: 10          # from recipe 02
    max_consecutive_failures: 3          # from recipe 03

  my-mcp-backup:
    mode: remote
    endpoint: "http://localhost:8081/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-3:                              # NEW: third instance
    mode: remote
    endpoint: "http://localhost:8082/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-group:
    mode: group
    strategy: round_robin                # NEW: changed from priority to round_robin
    min_healthy: 1
    members:
      - id: my-mcp
        weight: 1                        # NEW: equal weight
      - id: my-mcp-backup
        weight: 1                        # NEW: equal weight
      - id: my-mcp-3                     # NEW: third member
        weight: 1
```

## Try It

1. Start all three MCP server instances on ports 8080, 8081, 8082.

2. Start Hangar and confirm the group is configured (it stays COLD until the
   first call):

   ```bash
   mcp-hangar status
   ```

   ```
   ╭──────────────────────────────────────────────────────────────────────────────╮
   │ Server not running | McpServers: 1                                           │
   ╰──────────────────────────────────────────────────────────────────────────────╯
                MCP Hangar Status
   ╭─────┬───────────┬───────┬────────┬───────╮
   │     │ McpServer │ State │ Health │ Tools │
   ├─────┼───────────┼───────┼────────┼───────┤
   │ --  │ my-mcp-group │ COLD │      - │     - │
   ╰─────┴───────────┴───────┴────────┴───────╯
   ```

   `status` shows the group as a single COLD row -- it does not report the
   strategy or per-member health. To observe load distribution, watch which
   member serves successive calls in the logs (next step).

3. Make several tool calls through the group and observe distribution in
   the logs. Use the JSON-RPC approach from recipe 03:

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 2
   ) | mcp-hangar serve 2>/dev/null | grep '"id":2'
   ```

   Each call routes to a different member in round-robin order.

4. Stop one instance and observe redistribution:

   ```bash
   # Kill the process on port 8082, then re-run status
   mcp-hangar status
   ```

   ```
   ╭──────────────────────────────────────────────────────────────────────────────╮
   │ Server not running | McpServers: 1                                           │
   ╰──────────────────────────────────────────────────────────────────────────────╯
                MCP Hangar Status
   ╭─────┬───────────┬───────┬────────┬───────╮
   │     │ McpServer │ State │ Health │ Tools │
   ├─────┼───────────┼───────┼────────┼───────┤
   │ --  │ my-mcp-group │ COLD │      - │     - │
   ╰─────┴───────────┴───────┴────────┴───────╯
   ```

   `status` still reports the group as a single COLD row; it does not surface
   per-member health. Traffic automatically redistributes to the remaining two
   healthy members -- watch the logs to confirm calls only land on the survivors.

## What Just Happened

The `round_robin` strategy cycles through healthy members sequentially. Each request goes to the next member in the rotation. When a member fails health checks, it is removed from the rotation until it recovers.

Other available strategies:

| Strategy | Behavior |
|----------|----------|
| `round_robin` | Cycle through members sequentially |
| `random` | Random member selection |
| `least_connections` | Route to member with fewest active calls |
| `weighted_round_robin` | Respect `weight` field -- higher weight gets more traffic |
| `priority` | Route to lowest priority number (primary/backup pattern) |

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `strategy` | string | `round_robin` | Load balancing strategy |
| `members[].weight` | int | `1` | Relative routing weight (used by `weighted` strategy) |

## What's Next

Your MCP servers are balanced -- but what happens when one client sends 1000 requests per second? You need to protect your MCP servers from overload.

--> [06 -- Rate Limiting](06-rate-limiting.md)
