# 03 — Circuit Breaker

> **Prerequisite:** [02 — Health Checks](02-health-checks.md)
> **You will need:** Working setup from recipe 02
> **Time:** 15 minutes
> **Adds:** MCP Server groups with a circuit breaker that reports a failing group and takes failing members out of rotation

## The Problem

Health checks from recipe 02 run once a minute. Between checks, a flaky MCP server can accept requests, fail, get retried, fail again — wasting agent time and tokens on a MCP server that's clearly broken. Your MCP server responds to health checks (it's technically alive) but fails 80% of real tool calls. Intermittent failure. Health checks say READY. Agents suffer.

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

1. Restart the background Hangar on the new config

   ```bash
   kill %1    # the Hangar from recipe 02, if it still runs
   docker unpause mcp-math 2>/dev/null; docker start mcp-math
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 127.0.0.1 --port 8000 --log-file /tmp/hangar-circuit.log &
   sleep 5
   grep -E 'group_loaded|"task": "health_check"' /tmp/hangar-circuit.log
   ```

   ```
   {"group_id": "my-mcp-group", "member_count": 1, "strategy": "round_robin", "event": "group_loaded", ...}
   {"task": "health_check", "interval_s": 60, "event": "background_worker_started", ...}
   ```

   The worker's `interval_s=60` is not the `health_check_interval_s: 30` set
   above, and on 2.24.0 the 60 is the one that counts: the worker probes every
   READY server once a minute, and `health_check_interval_s` is recorded but
   not read by the scheduler
   ([mcp-hangar#1686](https://github.com/mcp-hangar/mcp-hangar/issues/1686)).

   The group starts its members when it loads, so `my-mcp` is already READY.

2. Call a tool successfully through the group

   The tool calls in this recipe and the next go to the background Hangar
   over Streamable HTTP. Its endpoint answers a lone `tools/call` without an
   `initialize` handshake, so one `curl` is one call. Save it as a helper:

   ```bash
   cat > /tmp/hangar-call.sh << 'EOF'
   #!/bin/bash
   # hangar-call.sh TOOL [ARGUMENTS-JSON]: one MCP tools/call to the Hangar on :8000
   ARGS="$2"; [ -z "$ARGS" ] && ARGS='{}'
   curl -s http://localhost:8000/mcp -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"'"$1"'","arguments":'"$ARGS"'}}' \
     | sed -n 's/^data: //p' | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["content"][0]["text"])'
   EOF
   chmod +x /tmp/hangar-call.sh

   /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"success"' | head -1
   ```

   ```
     "success": true,
   ```

   Circuit breaker is CLOSED (normal operation). Call succeeded.

3. Freeze the MCP server to simulate failures

   ```bash
   docker pause mcp-math
   ```

   MCP Server is now hung: it accepts connections and never answers.

4. Watch a call be refused — the key demonstration

   The refusal comes from rotation, not from the circuit. Keep talking to the
   one background Hangar: a group's breaker and its members' failure counts
   live in the process that saw them.

   ```bash
   for i in 2 3 4; do
     /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"error"' | head -1
     sleep 2
   done
   /tmp/hangar-call.sh hangar_group_list
   ```

   ```
         "error": "timeout: tools/call after 59.99...s",
         "error": "No available member in group 'my-mcp-group'",
         "error": "No available member in group 'my-mcp-group'",
   ```

   ```json
   {"group_id": "my-mcp-group", "state": "inactive", "min_healthy": 1,
    "healthy_count": 0, "members_in_rotation_count": 0, "total_members": 1,
    "is_available": false, "circuit_open": false, "members": [...]}
   ```

   Call 2 reached the frozen server and waited out the 60-second call timeout.
   While it waited, the once-a-minute health check -- which gives up after 5
   seconds -- failed too. That is two failures in a row, so the member left
   rotation at `health.unhealthy_threshold` (2 by default). Calls 3 and 4
   never reached a member at all: `select_member_for()` had nothing in
   rotation to select, so Hangar refused them with `NoAvailableMemberError` in
   milliseconds instead of waiting out another timeout.

   Read the last line again: `circuit_open` is `false`. The calls were refused
   with the circuit still closed. What refuses a call to a group is an empty
   rotation — never the breaker, which nothing on the call path asks.

   Freeze it with `docker pause`, not `docker stop`. On 2.24.0 a stopped
   remote server's health check does not count (recipe 02, step 5): two failed
   calls (`connection_failed`) still take it out of rotation, but nothing
   brings the run to 3, and the circuit in step 5 never opens.

5. What opening the circuit does change

   The circuit opens when the group's failures in a row reach
   `failure_threshold` (3 here). The refusals in step 4 do not get there: they
   are Hangar's own, not the member's, so they are not counted against it. A
   member out of rotation is still health-checked, and it is the next failing
   health check that brings the run to 3 and opens the circuit -- within a
   minute, on the health worker's next pass.

   Once it opens, `hangar_group_list` reports the same group like this:

   ```json
   {"group_id": "my-mcp-group", "state": "degraded", "min_healthy": 1,
    "healthy_count": 0, "members_in_rotation_count": 0, "total_members": 1,
    "is_available": false, "circuit_open": true, "members": [...]}
   ```

   `hangar_status` shows the group `degraded` with its circuit `open`, and
   `mcp_hangar_group_circuit_open{group="my-mcp-group"}` reads 1. That is the
   whole of it: what opening the circuit changes is what Hangar reports about
   the group, plus the `min_healthy` bar it now has to clear again to close.
   Which calls get refused does not change. In a group that still had a second
   member in rotation, the same open circuit would keep selecting it and keep
   serving calls — which is what stops a failing primary from taking a healthy
   backup down with it. Recipe 04 builds that group.

6. Restart the MCP server and wait for the retry

   ```bash
   docker unpause mcp-math
   echo "Waiting 35 seconds for Hangar to retry the server..."
   sleep 35
   grep -E 'recovered successfully|Circuit breaker closed' /tmp/hangar-circuit.log
   ```

   ```
   {"event": "Circuit breaker closed for group my-mcp-group: 1 member(s) in rotation", ...}
   {"event": "McpServer my-mcp recovered successfully after 3 retries", ...}
   ```

   Waiting alone never closes a group's circuit: it has no timer, and it
   never half-opens. It closes once `min_healthy` members (1 here) are back in
   rotation and one of them reports a success -- a passing health check, a call
   that succeeded, or a completed start.

   Here it is the completed start, not the health check. The failing health
   check that opened the circuit also left `my-mcp` `degraded`, and a degraded
   server is not probed: `health_check()` returns immediately unless the
   server is `ready`. So nothing is left to find `my-mcp` answering again.
   What recovers it is the restart Hangar armed when the server degraded and
   retries on a backoff; the retry that succeeds records `McpServerStarted`,
   which the group hears as the member's success, puts it back in rotation and
   closes the circuit. If Hangar ran out of retries and gave up on `my-mcp`,
   it is `[DEAD]` in `hangar_status`, and neither a health check nor a call
   brings it back. In this group a recovery probe does: while a group has no
   member to select, Hangar starts its dead members again every 30 seconds,
   backing off to 10 minutes (`group_recovery_probe_started` in the log).
   `hangar_start` does it at once.

7. Verify recovery

   ```bash
   /tmp/hangar-call.sh hangar_call '{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}' | grep '"success"' | head -1
   ```

   ```
     "success": true,
   ```

   Call succeeded. Circuit is CLOSED. Full recovery.

   A group's circuit has no reset timer. It closes once `min_healthy` members (here, 1) are back in rotation, after a passing health check, a successful call, or a completed start. `hangar_group_rebalance` closes it at once.

## What Just Happened

Hangar introduced **MCP server groups** — a logical grouping of one or more MCP servers with shared policies. The group has a circuit breaker that counts the group's failures in a row: a failed call through the group counts, and so does a failed health check. That is how the circuit opens in this recipe — step 5 above turns on the third failure, and it is a health check that raises it.

**Circuit breaker states:**

**CLOSED** (normal operation): All calls pass through to group members. The circuit breaker counts consecutive failures. When `failure_count` reaches `failure_threshold` (3), the circuit opens.

**OPEN** (the group reported failing): The group's state becomes `degraded`, `circuit_open` reads `true` and `is_available` reads `false` in `hangar_group_list` and `hangar_status`, and `mcp_hangar_group_circuit_open` reads 1. The open circuit does not reject calls on its own — nothing on the call path asks it. What rejects them here is that the group's only member is out of rotation, so `select_member_for()` has nothing to select and the call comes back `NoAvailableMemberError` in milliseconds instead of waiting out a timeout. A group whose other members are still in rotation keeps serving calls with the same circuit open. It stays open until `min_healthy` members (1) are back in rotation and one reports a success, after a passing health check or a call that succeeded. There is no timer and no half-open probe.

**How this differs from health checks:**

- **Health checks** (recipe 02): a periodic probe (`tools/list`) of one server. Detects "is the MCP server alive?"
- **Circuit breaker** (recipe 03): a count of the group's failures in a row, across its members. Detects "is this group failing?"

They are not independent: a health check that fails is reported to every group the server belongs to, as a failure against that member, so health checks feed the breaker rather than bypassing it. What the breaker adds is that a failed call counts too, without waiting for the next probe — so a server that answers `tools/list` and still fails real work is caught.

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
