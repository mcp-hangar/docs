# Runbook: MCP server unhealthy / degraded

**Alerts:** `MCPHangarProviderUnhealthy` (critical, `consecutive_failures > 5`) · `MCPHangarProviderDegraded` (warning, `mcp_server_state == 3`).

## What it means

An MCP server is failing health checks repeatedly (state DEGRADED). Hangar will
stop routing to it once it is unhealthy.

## Diagnose

```promql
mcp_hangar_health_check_consecutive_failures
mcp_hangar_mcp_server_state                                # 3 = DEGRADED
histogram_quantile(0.95, sum by (le, mcp_server) (rate(mcp_hangar_health_check_duration_seconds_bucket[5m])))
```

```bash
curl -s -H "X-API-Key: $KEY" <hangar>/api/mcp_servers/<id>/health
curl -s -H "X-API-Key: $KEY" <hangar>/api/mcp_servers/<id>/logs?lines=200
```

## Remediate

- Container mode: check the pod/process — crashloop, bad image, missing env/secret.
- Remote mode: check reachability/TLS/auth to the upstream endpoint (`MCPHangarRemoteProviderUnreachable`).
- Transient → it recovers on the next successful health check and returns to READY.

## Escalate

Server owner if it's a specific integration; platform on-call if many servers degrade at once (shared dependency / DNS).
