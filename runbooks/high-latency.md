# Runbook: high tool-call latency

**Alerts:** `MCPHangarHighLatencyP95` (P95 > 3s) · `MCPHangarHighLatencyP99` (P99 > 5s) · `MCPHangarHighLatencyByTool`.

## What it means

Tool-call latency percentiles are above target. Calls succeed but are slow.

## Diagnose

```promql
histogram_quantile(0.95, sum by (le) (rate(mcp_hangar_tool_call_duration_seconds_bucket[5m])))
histogram_quantile(0.95, sum by (le, mcp_server) (rate(mcp_hangar_tool_call_duration_seconds_bucket[5m])))
histogram_quantile(0.95, sum by (le) (rate(mcp_hangar_mcp_server_cold_start_seconds_bucket[5m])))  # cold starts?
```

Note: failed calls currently record a 0s observation, which pulls percentiles DOWN —
a real latency problem may be worse than the graph shows (tracked in the metrics cleanup).

## Remediate

- Cold-start dominated (`MCPHangarFrequentColdStarts`) → increase idle TTL / keep hot.
- One slow upstream (`mcp_server` label) → work the upstream's performance.
- Concurrency wait high (`mcp_hangar_batch_concurrency_wait_seconds`) → raise concurrency limits.

## Escalate

If latency breaches the SLO budget sustainedly, treat as a degradation incident.
