# Runbook: MCP Hangar not responding

**Alerts:** `MCPHangarNotResponding` (critical) · `MCPHangarAllProvidersDown` (critical)

## What it means

Prometheus cannot scrape the Hangar (`up{job="mcp-hangar"} == 0`) for 1m, or every
registered MCP server is down while at least one is configured. The gateway is
effectively unavailable to clients.

## Impact

All tool calls fail. This is a user-facing outage.

## Diagnose

```bash
kubectl -n <ns> get pods -l app.kubernetes.io/name=mcp-hangar
kubectl -n <ns> describe pod <pod>          # crashloop / OOMKilled / probe failures
kubectl -n <ns> logs <pod> --tail=200
kubectl -n <ns> get endpoints <svc>         # is the Service backed by a ready pod?
```

```promql
up{job="mcp-hangar"}
sum(mcp_hangar_mcp_server_up)               # 0 while mcp_hangar_mcp_server_info > 0 ?
```

Check readiness: `GET /health/ready` reflects event-store durability posture — a
not-ready pod is pulled from the Service.

## Remediate

- Crashloop → fix the failing dependency shown in logs; roll back the last deploy if it correlates.
- OOMKilled → raise memory limits (see `MCPHangarHighMemoryUsage`).
- All-providers-down → the servers are the problem, not Hangar; work `provider-unhealthy`.
- Scrape-only failure (app healthy) → check the ServiceMonitor/NetworkPolicy `allowMonitoring`.

## Escalate

If not resolved in 15m or the root cause is infrastructural (node, network, registry), page the platform on-call.
