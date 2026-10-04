# Runbook: MCP server unhealthy / degraded

**Alerts:** `MCPHangarProviderDegraded` (warning, `mcp_hangar_mcp_server_state == 3` for 5m). The chart's `MCPHangarProviderNotSeenHealthy` also links here; it is described in [provider-dead](provider-dead.md).

## What it means

An MCP server's consecutive failures, usually failed health checks, reached
`max_consecutive_failures` (default 3), and it is DEGRADED. While it is degraded, Hangar refuses calls to it
with `CircuitBreakerOpen` (see [circuit-breaker](circuit-breaker.md)), and the
recovery saga restarts it with a growing delay.

## Diagnose

```promql
mcp_hangar_health_check_consecutive_failures
mcp_hangar_mcp_server_state                                # 3 = DEGRADED
histogram_quantile(0.95, sum by (le, mcp_server) (rate(mcp_hangar_health_check_duration_seconds_bucket[5m])))
```

```bash
curl -s -H "X-API-Key: $KEY" "<hangar>/api/mcp_servers/<id>/health"
curl -s -H "X-API-Key: $KEY" "<hangar>/api/mcp_servers/<id>/logs?lines=200"
```

Hangar's log shows the path: `mcp_server_degraded_by_health_check: <id>`, then
`McpServer <id> degraded, scheduling retry 1/3 in 5.0s`, and either
`McpServer <id> recovered successfully after <n> retries` or `mcp_server_given_up`.

## Remediate

- Container mode: check the pod/process — crashloop, bad image, missing env/secret.
- Remote mode: check reachability/TLS/auth to the upstream endpoint (`MCPHangarRemoteProviderUnreachable`). In 2.24.0 a refused connection does not fail a remote server's health check (#1698), so a stopped remote upstream can stay READY; its tool-call errors are the signal.
- Transient → a restart by the recovery saga succeeds and the server returns to READY.
- Not transient → when the saga runs out of retries the server reads DEAD (4), `MCPHangarProviderDegraded` resolves and `MCPHangarProviderDead` fires; work [provider-dead](provider-dead.md).

## Escalate

Server owner if it's a specific integration; platform on-call if many servers degrade at once (shared dependency / DNS).
