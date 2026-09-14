# Runbook: MCP server dead

**Alerts:** `MCPHangarProviderDead` (critical, `mcp_server_state == 4` for 1m) · `MCPHangarProviderNotSeenHealthy` (warning, not seen working for 15m while not cold).

Both need Hangar 2.20.0 or later. Before it, a server Hangar gave up on read
`cold` (0), and the last-healthy gauge did not exist.

## What it means

The server failed and is not running, and nothing restarts it on its own:
health checks skip a dead server, and the recovery saga has cancelled its
restarts. A server gets here four ways, and Hangar records which:

| Reason | How it got here | Hangar log event |
| --- | --- | --- |
| `given_up` | The recovery saga ran out of retries on a degraded server | `mcp_server_given_up` |
| `crashed` | A health check found its connection dead | `mcp_server_dead` |
| `start_failed` | A start failed, below `max_consecutive_failures` | `mcp_server_start_failed` |
| `capability_blocked` | It exposed tools it did not declare, with enforcement mode `block` | `capability_drift_detected` with `enforcement_mode=block` |

`MCPHangarProviderNotSeenHealthy` fires for a server that is not cold and has
had no passing health check, completed start or successful tool call for 15
minutes. That is a dead server (4), one still being retried (3), or one stuck
starting (1): `mcp_hangar_mcp_server_state` tells you which. A server that was
never healthy has no last-healthy series, so only `MCPHangarProviderDead`
catches it.

With more than one replica, each reports its own servers: the `instance` label
says which replica has the server dead.

## Diagnose

```promql
mcp_hangar_mcp_server_state == 4                                   # 4 = DEAD, by mcp_server and instance
time() - mcp_hangar_mcp_server_last_healthy_timestamp_seconds      # seconds since Hangar last saw it working
```

The reason is not on a metric and not in `hangar_details`. Hangar's own log
names it: search it for the server id and the events in the table above. For a
group member, the group also logs `Member <id> dead in group <group>: <reason>`.

```bash
curl -s -H "X-API-Key: $KEY" <hangar>/api/mcp_servers/<id>/logs?lines=200   # the server's own recent output
```

`hangar_details` on the server shows `state: dead` and its `health` block:
`consecutive_failures`, `last_failure_ago`, and `can_retry`, which is `false`
while its backoff lasts.

## What starts it again

`dead` is not terminal. Why it died decides:

| Reason | A call through a group | A call naming it | A deliberate start |
| --- | --- | --- | --- |
| `given_up` | never | yes, after its backoff | yes |
| `capability_blocked` | never | never | yes |
| `crashed`, `start_failed` | yes, after its backoff | yes, after its backoff | yes |

A call inside the backoff is refused with `CircuitBreakerOpen` and the time to
wait. The deliberate starts are `hangar_start` on the server or on its group,
`POST /api/mcp_servers/<id>/start`, `hangar_warm` naming the server, a group
adding the server with auto-start, and a failover saga starting the backup it
was configured with. `hangar_warm` with no names skips dead servers and lists
them in `skipped_dead`.

A group does not count a dead member as healthy. A member Hangar gave up on, or
one a capability block stopped, leaves rotation until a successful start puts
it back, subject to the group's `healthy_threshold`.

## Remediate

1. Fix what the reason points to: the upstream, its command or image, its
   credentials or its network. For `capability_blocked`, compare the tools it
   exposes with the tools it declares before starting it again.
2. Start it deliberately, with `hangar_start` or
   `POST /api/mcp_servers/<id>/start`.
3. Watch `mcp_hangar_mcp_server_state` return to 2 and
   `mcp_hangar_mcp_server_last_healthy_timestamp_seconds` move.

`hangar_stop` makes a dead server `cold`, which clears `MCPHangarProviderDead`
without fixing anything.

## Escalate

Server owner if it is one integration; platform on-call if many servers go dead
at once (a shared dependency, network or DNS). Treat `capability_blocked` as a
security signal: tell the server's owner before starting it again.
