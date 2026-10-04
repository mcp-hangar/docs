# Runbooks

Operational runbooks for the alerts shipped with MCP Hangar
(`helm-charts` → `prometheusRule.enabled`, source in
[`mcp-hangar/files/prometheus-alerts.yaml`](https://github.com/mcp-hangar/helm-charts/blob/main/mcp-hangar/files/prometheus-alerts.yaml)).
Most alerts link here through their `runbook_url` annotation. `MCPHangarHighLatencyP99`
and `MCPHangarHighLatencyByTool` carry none; their runbook is high-latency.

| Runbook | Alerts |
| --------- | -------- |
| [not-responding](not-responding.md) | `MCPHangarNotResponding`, `MCPHangarAllProvidersDown` |
| [high-error-rate](high-error-rate.md) | `MCPHangarHighErrorRate` |
| [batch-failures](batch-failures.md) | `MCPHangarBatchHighFailureRate` |
| [circuit-breaker](circuit-breaker.md) | `MCPHangarCircuitBreakerTripped` |
| [provider-unhealthy](provider-unhealthy.md) | `MCPHangarProviderDegraded` |
| [provider-dead](provider-dead.md) | `MCPHangarProviderDead`, `MCPHangarProviderNotSeenHealthy` (its `runbook_url` points to provider-unhealthy) |
| [health-failures](health-failures.md) | `MCPHangarHighConsecutiveFailures` |
| [high-latency](high-latency.md) | `MCPHangarHighLatencyP95/P99/ByTool` |

Not tied to one alert: [tracing-diagnosis](tracing-diagnosis.md) finds a request in a
trace backend, explains a gate decision, and separates sampling from dropped or
missing export. Start there when `MCPHangarTelemetryExportFailing` fires.

See also: [Observability guide](../guides/OBSERVABILITY.md) · [Release runbook](RELEASE.md).
