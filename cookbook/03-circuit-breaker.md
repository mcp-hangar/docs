# 03 — Circuit Breaker

> **Prerequisite:** [02 — Health Checks](02-health-checks.md)
> **You will need:** Working setup from recipe 02
> **Time:** 15 minutes
> **Adds:** MCP Server groups with a circuit breaker that reports a failing group and takes failing members out of rotation

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

4. Watch a call be refused — the key demonstration

   The refusal comes from rotation, not from the circuit. Keep the whole thing
   in one session: each `serve` pipeline is a new Hangar process, and a group's
   breaker and its members' failure counts live in the process that saw them.

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     for i in 2 3 4; do
       echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":'"$i"'}'
       sleep 2
     done
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_group_list","arguments":{}},"id":9}'
     sleep 2
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>&1 \
     | grep -E 'NoAvailableMemberError|"id":9'
   ```

   ```
   (error output — NoAvailableMemberError: No available member in group 'my-mcp-group')
   ```

   ```json
   {"group_id": "my-mcp-group", "state": "inactive", "min_healthy": 1,
    "healthy_count": 0, "members_in_rotation_count": 0, "total_members": 1,
    "is_available": false, "circuit_open": false, "members": [...]}
   ```

   Calls 2 and 3 reached the MCP server and failed, which is two failures, so
   the member left rotation at `health.unhealthy_threshold` (2 by default).
   Call 4 never reached a member at all: `select_member_for()` had nothing in
   rotation to select, so Hangar refused it with `NoAvailableMemberError` in
   milliseconds instead of waiting out a connection timeout.

   Read the last line again: `circuit_open` is `false`. The call was refused
   with the circuit still closed. What refuses a call to a group is an empty
   rotation — never the breaker, which nothing on the call path asks.

5. What opening the circuit does change

   The circuit opens when the group's failures in a row reach
   `failure_threshold` (3 here). Three failed calls will not get there in this
   group: the member leaves rotation after two, and the refusals that follow
   are Hangar's own, not the member's, so they are not counted against it. A
   member out of rotation is still health-checked, and it is the next failing
   health check that brings the run to 3 and opens the circuit. How long that
   takes is `health_check_interval_s`.

   Once it opens, `hangar_group_list` reports the same group like this:

   ```json
   {"group_id": "my-mcp-group", "state": "degraded", "min_healthy": 1,
    "healthy_count": 0, "members_in_rotation_count": 0, "total_members": 1,
    "is_available": false, "circuit_open": true, "members": [...]}
   ```

   `hangar_status` shows the group `[DEGRADED]` with `CIRCUIT open`, and
   `mcp_hangar_group_circuit_open{group="my-mcp-group"}` reads 1. That is the
   whole of it: what opening the circuit changes is what Hangar reports about
   the group, plus the `min_healthy` bar it now has to clear again to close.
   Which calls get refused does not change. In a group that still had a second
   member in rotation, the same open circuit would keep selecting it and keep
   serving calls — which is what stops a failing primary from taking a healthy
   backup down with it. Recipe 04 builds that group.

6. Restart the MCP server and wait for the retry

   ```bash
   docker start mcp-math
   echo "Waiting 35 seconds for Hangar to retry the server..."
   sleep 35
   tail -5 /tmp/hangar-circuit.log
   ```

   Waiting alone never closes a group's circuit: it has no timer, and it
   never half-opens. It closes once `min_healthy` members (1 here) are back in
   rotation and one of them reports a success -- a passing health check, a call
   that succeeded, or a completed start.

   Here it is the completed start, not the health check. The failing health
   check that opened the circuit also left `my-mcp` `degraded`, and a degraded
   server is not health-checked at all: `health_check()` returns immediately
   unless the server is `ready`. So nothing is left to find `my-mcp` answering
   again. What recovers it is the restart Hangar armed when the server
   degraded and retries on a backoff; the retry that succeeds records
   `McpServerStarted`, which the group hears as the member's success, puts it
   back in rotation and closes the circuit. If Hangar ran out of retries and
   gave up on `my-mcp`, `hangar_status` shows it `[DEAD]`, and neither a health
   check nor a call brings it back: start it with `hangar_start`.

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

   A group's circuit has no reset timer. It closes once `min_healthy` members (here, 1) are back in rotation, after a passing health check, a successful call, or a completed start. `hangar_group_rebalance` closes it at once.

## What Just Happened

Hangar introduced **MCP server groups** — a logical grouping of one or more MCP servers with shared policies. The group has a circuit breaker that tracks real tool call failures, not synthetic health probes.

**Circuit breaker states:**

**CLOSED** (normal operation): All calls pass through to group members. The circuit breaker counts consecutive failures. When `failure_count` reaches `failure_threshold` (3), the circuit opens.

**OPEN** (the group reported failing): The group's state becomes `degraded`, `circuit_open` reads `true` and `is_available` reads `false` in `hangar_group_list` and `hangar_status`, and `mcp_hangar_group_circuit_open` reads 1. The open circuit does not reject calls on its own — nothing on the call path asks it. What rejects them here is that the group's only member is out of rotation, so `select_member_for()` has nothing to select and the call comes back `NoAvailableMemberError` in milliseconds instead of waiting 10+ seconds for a connection timeout. A group whose other members are still in rotation keeps serving calls with the same circuit open. It stays open until `min_healthy` members (1) are back in rotation and one reports a success, after a passing health check or a call that succeeded. There is no timer and no half-open probe.

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
