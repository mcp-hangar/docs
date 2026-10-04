# Runbook: rising consecutive health failures

**Alert:** `MCPHangarHighConsecutiveFailures` (warning, `mcp_hangar_health_check_consecutive_failures >= 1` for 2m).

## What it means

A server's health checks are failing. At `max_consecutive_failures` (default 3)
the server goes DEGRADED (3) and the recovery saga starts restarting it. Each
failed restart adds to the gauge, and a dead server is no longer checked, so the
gauge holds its value until a check passes. The alert therefore keeps firing
next to `MCPHangarProviderDegraded` and `MCPHangarProviderDead`; on its own, it
is the early warning before them.

Health checks run every 60 seconds; a per-server `health_check_interval_s` is
not applied in 2.24.0 (#1686).

## Diagnose

```promql
mcp_hangar_health_check_consecutive_failures > 0
mcp_hangar_mcp_server_state                               # 2 = READY, 3 = DEGRADED, 4 = DEAD
sum by (mcp_server, result) (rate(mcp_hangar_health_checks_total[5m]))
```

Hangar's log names the failure: `health_check_failed: <id>, error_type=<type>`,
for example `TimeoutError` for an upstream that stopped answering.

## Remediate

Same first steps as [provider-unhealthy](provider-unhealthy.md), earlier: inspect
the server's logs and health, and watch whether failures clear on their own.
Often a slow or restarting upstream.

## Escalate

Once the server reads DEGRADED (3), follow [provider-unhealthy](provider-unhealthy.md);
once it reads DEAD (4), follow [provider-dead](provider-dead.md).
