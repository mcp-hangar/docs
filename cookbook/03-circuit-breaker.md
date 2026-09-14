# 03 — Circuit Breaker

> **Prerequisite:** [02 — Health Checks](02-health-checks.md)
> **You will need:** Working setup from recipe 02
> **Time:** 15 minutes
> **Adds:** MCP Server groups with circuit breaker for fast-fail protection

## The Problem

Health checks from recipe 02 run every 30 seconds. Between checks, a flaky MCP server can accept requests, fail, get retried, fail again — wasting agent time and tokens on a MCP server that's clearly broken. Your MCP server responds to health checks (it's technically alive) but fails 80% of real tool calls. Intermittent failure. Health checks say READY. Agents suffer.

Health checks tell you the patient is dead. Circuit breakers stop you from performing surgery on a corpse.

## The Config

```yaml
# config.yaml — Recipe 03: Circuit Breaker

mcp_servers:
  my-mcp:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "My remote MCP server"
    health_check_interval_s: 30
    max_consecutive_failures: 3
    http:
      connect_timeout: 10.0
      read_timeout: 30.0

  my-mcp-group:                            # NEW: added in this recipe
    mode: group                            # NEW: added in this recipe
    description: "My MCP group with circuit breaker"  # NEW: added in this recipe
    strategy: round_robin                  # NEW: added in this recipe
    min_healthy: 1                         # NEW: added in this recipe
    circuit_breaker:                       # NEW: added in this recipe
      failure_threshold: 3                 # NEW: added in this recipe
    members:                               # NEW: added in this recipe
      - id: my-mcp                         # NEW: added in this recipe
```

Save this as `~/.config/mcp-hangar/config.yaml` (or update your existing file).

## Try It

1. Start Hangar with the new config

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --log-file /tmp/hangar-circuit.log &
   ```

   ```
   INFO     group_loaded group_id=my-mcp-group member_count=2 strategy=round_robin
   INFO     background_worker_started task=health_check interval_s=60
   ```

2. Call a tool successfully through the group

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 3
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>&1 | grep -E '"id":2|circuit'
   ```

   ```json
   {"jsonrpc":"2.0","id":2,"result":{"content":[...]}}
   ```

   Circuit breaker is CLOSED (normal operation). Call succeeded.

3. Stop the MCP server to simulate failures

   ```bash
   docker stop mcp-math
   ```

   MCP Server is now dead.

4. Call the tool 3 times to trip the circuit

   ```bash
   for i in 1 2 3; do
     echo "Attempt $i..."
     (
       echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
       sleep 0.5
       echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
       sleep 0.5
       echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
       sleep 3
     ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>&1 | grep -E 'error|circuit' | head -2
   done
   ```

   ```
   Attempt 1...
   (error output — connection refused or timeout)
   Attempt 2...
   (error output — connection refused or timeout)
   Attempt 3...
   (error output — circuit breaker opened after 3 failures)
   ```

   After 3 failures, circuit opens.

5. Verify fast-fail behavior — the key demonstration

   ```bash
   time (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 1
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>&1 | grep -E 'circuit_open|rejected'
   ```

   ```
   (error output — request rejected immediately, circuit is open)

   real    0m2.1s
   ```

   Request rejected in ~2 seconds (no 30-second timeout). This is the protection.

6. Restart the MCP server and wait for a health check

   ```bash
   docker start mcp-math
   echo "Waiting 35 seconds for the next health check..."
   sleep 35
   tail -5 /tmp/hangar-circuit.log
   ```

   Waiting alone never closes a group's circuit: it has no timer, and it never half-opens. It closes once `min_healthy` members (1 here) are back in rotation. A member comes back through a passing health check or a completed start, so the check that finds `my-mcp` answering again closes the circuit. If Hangar gave up on `my-mcp` while it was down, `hangar_status` shows it `[DEAD]` and health checks skip it: start it with `hangar_start`.

7. Verify recovery

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 3
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>&1 | grep -E '"id":2|success'
   ```

   ```json
   {"jsonrpc":"2.0","id":2,"result":{"content":[...]}}
   ```

   Call succeeded. Circuit is CLOSED. Full recovery.

## What Just Happened

Hangar introduced **MCP server groups** — a logical grouping of one or more MCP servers with shared policies. The group has a circuit breaker that tracks real tool call failures, not synthetic health probes.

**Circuit breaker states:**

**CLOSED** (normal operation): All calls pass through to group members. The circuit breaker counts consecutive failures. When `failure_count` reaches `failure_threshold` (3), the circuit opens.

**OPEN** (protecting): All calls are rejected immediately with `NoAvailableMemberError`. No traffic reaches the MCP server — this is the protection. Instead of waiting 10+ seconds for connection timeout, Hangar fails in milliseconds. It stays open until `min_healthy` members are back in rotation, after a passing health check or a completed start. There is no timer and no half-open probe.

**How this differs from health checks:**

- **Health checks** (recipe 02): Periodic synthetic probe (`tools/list` every 30s). Detects "is the MCP server alive?"
- **Circuit breaker** (recipe 03): Tracks real tool call failures in real-time. Detects "is the MCP server working?"

They complement each other. Health checks catch dead MCP servers. Circuit breakers catch flaky MCP servers that pass health checks but fail real requests. The circuit breaker trips instantly on the Nth failure — no waiting for the next health check cycle.

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `mcp_servers.<name>.mode` | string | — | Set to `group` for MCP server groups |
| `mcp_servers.<name>.strategy` | string | `round_robin` | Load balancing strategy |
| `mcp_servers.<name>.min_healthy` | int | `1` | Minimum healthy members required |
| `mcp_servers.<name>.circuit_breaker.failure_threshold` | int | `10` | Consecutive failures before circuit opens |
| `mcp_servers.<name>.members` | list | — | List of MCP server IDs or inline definitions |

## Running More Than One Hangar

The breaker lives in the process that opened it. Each replica decides for itself
whether it can reach an upstream, so a breaker opened on one pod does not open
on its peers -- deliberately, because a single replica with a network problem
must not cut a healthy server off from the rest of the fleet. The cost is that
each replica discovers an outage independently, and that `GET /api/system` on
one pod can report a server the others are still using. See
[25 -- Running More Than One Replica](25-multiple-replicas.md).

For a group, each replica exposes its own circuit as
`mcp_hangar_group_circuit_open{group}`, and the scrape's `instance` label tells
the replicas apart. [MCP Server Groups → More Than One
Replica](../guides/MCP_SERVER_GROUPS.md#more-than-one-replica) has the queries
that find replicas disagreeing about a group.

## What's Next

Your single MCP server is protected — but it's still a single point of failure. When the circuit opens, agents get errors instead of results. What if there was a backup MCP server ready to take over automatically?

→ [04 — Failover](04-failover.md)
