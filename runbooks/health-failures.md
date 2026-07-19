# Runbook: rising consecutive health failures

**Alert:** `MCPHangarHighConsecutiveFailures` (warning, `consecutive_failures > 2`).

## What it means

An early-warning signal: a server is starting to fail health checks but has not yet
crossed the DEGRADED threshold. Catch it before it becomes a `provider-unhealthy` page.

## Diagnose

```promql
mcp_hangar_health_check_consecutive_failures > 0
sum by (mcp_server, result) (rate(mcp_hangar_health_checks_total[5m]))
```

## Remediate

Same first steps as `provider-unhealthy`, earlier: inspect the server's logs/health,
watch whether failures clear on their own. Often a slow/restarting upstream.

## Escalate

Only if it climbs toward the DEGRADED threshold — then follow `provider-unhealthy`.
