# Runbook: high tool-call error rate

**Alert:** `MCPHangarHighErrorRate` (critical) — tool-call error ratio exceeds the threshold for 2m.

## What it means

`rate(mcp_hangar_tool_call_errors_total) / rate(mcp_hangar_tool_calls_total)` is above 10%:
a large fraction of proxied tool calls are failing. Both are labelled by the server that
took the call, the member for a call to a group. A call refused by a batch gate is in neither.

## Impact

Clients see failures on a significant share of calls; degraded, not down.

## Diagnose

```promql
topk(10, sum by (mcp_server, error_type) (rate(mcp_hangar_tool_call_errors_total[5m])))
sum by (mcp_server) (rate(mcp_hangar_tool_call_errors_total[5m]))
  / sum by (mcp_server) (rate(mcp_hangar_tool_calls_total[5m]))
```

Isolate: is it one server (`mcp_server` label) or one class (`error_type`)? `error_type`
is the upstream's JSON-RPC error code (`-32000`, `-1`) when the upstream answered with an
error, and Hangar's exception name (`TimeoutError`, `McpServerStartError`) otherwise. Then:

```bash
# gateway readiness; the image has no curl or wget, so use its python3
kubectl -n <ns> exec <pod> -- python3 -c 'import urllib.request as u; print(u.urlopen("http://localhost:8080/health/ready").read().decode())'
# tail the offending server's captured stderr (secrets are redacted):
curl -s -H "X-API-Key: $KEY" "<hangar>/api/mcp_servers/<id>/logs?lines=200"
```

## Remediate

- One upstream failing → restart/repair it; consider blocking it if it's poisoning batches.
- Timeouts (`error_type`) → check upstream latency (`high-latency`) and per-server timeout config.
- Auth/4xx from upstream → credential or token-issuer problem.

## Escalate

Sustained > 10 min across multiple servers → page. Note: the alert threshold (10%)
is looser than the documented 1% SLO — reconcile once SLO burn-rate alerts land.
