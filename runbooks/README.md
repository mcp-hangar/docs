# Runbooks

Operational runbooks for the alerts shipped with MCP Hangar
(`helm-charts` → `prometheusRule.enabled`, source in
[`mcp-hangar/files/prometheus-alerts.yaml`](https://github.com/mcp-hangar/helm-charts/blob/main/mcp-hangar/files/prometheus-alerts.yaml)).
Each critical alert links here via its `runbook_url` annotation.

| Runbook | Alerts |
| --------- | -------- |
| [not-responding](not-responding.md) | `MCPHangarNotResponding`, `MCPHangarAllProvidersDown` |
| [high-error-rate](high-error-rate.md) | `MCPHangarHighErrorRate` |
| [batch-failures](batch-failures.md) | `MCPHangarBatchHighFailureRate` |
| [circuit-breaker](circuit-breaker.md) | `MCPHangarCircuitBreakerTripped` |
| [provider-unhealthy](provider-unhealthy.md) | `MCPHangarProviderUnhealthy`, `MCPHangarProviderDegraded` |
| [health-failures](health-failures.md) | `MCPHangarHighConsecutiveFailures` |
| [high-latency](high-latency.md) | `MCPHangarHighLatencyP95/P99/ByTool` |
| [detection-match](detection-match.md) | `MCPHangarCriticalDetectionMatch` |

See also: [Observability guide](../guides/OBSERVABILITY.md) · [Release runbook](RELEASE.md).
