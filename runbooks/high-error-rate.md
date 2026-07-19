# Runbook: high tool-call error rate

**Alert:** `MCPHangarHighErrorRate` (critical) — tool-call error ratio exceeds the threshold for 2m.

## What it means

`rate(mcp_hangar_tool_call_errors_total) / rate(mcp_hangar_tool_calls_total)` is high:
a large fraction of proxied tool calls are failing.

## Impact

Clients see failures on a significant share of calls; degraded, not down.

## Diagnose

```promql
topk(10, sum by (mcp_server, error_type) (rate(mcp_hangar_tool_call_errors_total[5m])))
sum by (mcp_server) (rate(mcp_hangar_tool_call_errors_total[5m]))
  / sum by (mcp_server) (rate(mcp_hangar_tool_calls_total[5m]))
```

Isolate: is it one server (`mcp_server` label) or one class (`error_type`)? Then:

```bash
kubectl -n <ns> exec <pod> -- curl -s localhost:8080/health   # gateway health
# tail the offending server's captured stderr (secrets are redacted):
curl -s -H "X-API-Key: $KEY" <hangar>/api/mcp_servers/<id>/logs?lines=200
```

## Remediate

- One upstream failing → restart/repair it; consider blocking it if it's poisoning batches.
- Timeouts (`error_type`) → check upstream latency (`high-latency`) and per-server timeout config.
- Auth/4xx from upstream → credential or token-issuer problem.

## Escalate

Sustained > 10 min across multiple servers → page. Note: the alert threshold (10%)
is looser than the documented 1% SLO — reconcile once SLO burn-rate alerts land.
