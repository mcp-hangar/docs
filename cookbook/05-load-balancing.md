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
    max_consecutive_failures: 3          # from recipe 02

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

1. Start a third instance beside the two from recipe 04:

   ```bash
   docker run -d --name mcp-3 -p 8082:8080 mcp-math:latest
   ```

2. Restart the background Hangar on the new config, and
   confirm the group is configured:

   ```bash
   kill %1    # the Hangar from recipe 04
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 127.0.0.1 --port 8000 --log-file /tmp/hangar-lb.log &
   sleep 5
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml status
   ```

   ```
   ╭──────────────────────────────────────────────────────────────────────────────╮
   │ Server not running | MCP servers: 4                                          │
   ╰──────────────────────────────────────────────────────────────────────────────╯
                  MCP Hangar Status
   ╭─────┬───────────────┬───────┬────────┬───────╮
   │     │ MCP server    │ State │ Health │ Tools │
   ├─────┼───────────────┼───────┼────────┼───────┤
   │ --  │ my-mcp        │ COLD  │      - │     - │
   │ --  │ my-mcp-backup │ COLD  │      - │     - │
   │ --  │ my-mcp-3      │ COLD  │      - │     - │
   │ --  │ my-mcp-group  │ COLD  │      - │     - │
   ╰─────┴───────────────┴───────┴────────┴───────╯
   ```

   The count is four, not one: the members are servers in their own right and
   `status` lists them alongside the group. `status` reads the config file, not
   the running gateway, so every row reads COLD whatever the gateway is doing,
and the header says `Server not running` while it runs: `status` asks for a
`/health` route the gateway does not serve
([mcp-hangar#1659](https://github.com/mcp-hangar/mcp-hangar/issues/1659)).
   The gateway itself started all three members when it loaded the group;
   `hangar_group_list` shows them `ready` and in rotation:

   ```bash
   /tmp/hangar-call.sh hangar_group_list | grep -E '"id"|in_rotation'
   ```

3. Make six tool calls through the group and count where they landed. Each
   call is counted against the member that served it:

   ```bash
   for i in 1 2 3 4 5 6; do
     /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' > /dev/null
   done
   curl -s http://localhost:8000/metrics | grep '^mcp_hangar_tool_calls_total'
   ```

   ```
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="success",tool="add"} 2.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-backup",status="success",tool="add"} 2.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-3",status="success",tool="add"} 2.0
   ```

   Two each: round robin.

4. Stop one instance and run the same six calls again:

   ```bash
   docker stop mcp-3
   for i in 1 2 3 4 5 6; do
     /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"error"' | head -1
   done
   curl -s http://localhost:8000/metrics | grep '^mcp_hangar_tool_calls_total'
   ```

   ```
         "error": null,
         "error": null,
         "error": "connection_failed: [Errno 61] Connection refused",
         "error": null,
         "error": null,
         "error": "connection_failed: [Errno 61] Connection refused",
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="success",tool="add"} 4.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-backup",status="success",tool="add"} 4.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-3",status="success",tool="add"} 2.0
   mcp_hangar_tool_calls_total{mcp_server="my-mcp-3",status="error",tool="add"} 2.0
   ```

   Round robin kept sending every third call to `my-mcp-3` until two of them
   had failed (`health.unhealthy_threshold`, 2 by default). That took it out
   of rotation, and from here on traffic is split between the two survivors.
   The failed calls are not retried on another member. `hangar_group_list`
   now shows `my-mcp-3` with `"in_rotation": false`.

## What Just Happened

The `round_robin` strategy cycles through healthy members sequentially. Each request goes to the next member in the rotation. When a member fails -- two failed calls in a row, or a failed health check -- it is removed from the rotation until a success brings it back.

Other available strategies:

| Strategy | Behavior |
| ---------- | ---------- |
| `round_robin` | Cycle through members sequentially |
| `random` | Random member selection, weighted by `weight` |
| `least_connections` | Route to the member selected least recently (a stand-in for "fewest connections"; active calls are not counted) |
| `weighted_round_robin` | Respect `weight` field -- higher weight gets more traffic |
| `priority` | Route to lowest priority number (primary/backup pattern) |

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `strategy` | string | `round_robin` | Load balancing strategy |
| `members[].weight` | int | `1` | Relative routing weight (used by `weighted_round_robin` and `random`) |

## What's Next

Your MCP servers are balanced -- but what happens when one client sends 1000 requests per second? You need to protect your MCP servers from overload.

--> [06 -- Rate Limiting](06-rate-limiting.md)
