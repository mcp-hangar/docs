# 07 -- Observability: Metrics

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar in HTTP mode, your own Prometheus and Grafana
> **Time:** 10 minutes
> **Adds:** Prometheus metrics and Grafana dashboards
> **Concept:** [Governance observability](https://mcp-hangar.io/learn/governance-observability)

## The Problem

You have MCP servers running. You don't know how many tool calls they handle, how long calls take, or whether health checks are passing. When something breaks at 3 AM, you need data, not guesses.

## The Config

```yaml
# config.yaml -- Recipe 07: Observability Metrics
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: "http://localhost:8080/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3
```

No config changes needed -- metrics are always available at `/metrics` on the HTTP server.

## Try It

1. Start Hangar in HTTP mode:

   ```bash
   mcp-hangar serve --config ~/.config/mcp-hangar/config.yaml \
     --http --host 127.0.0.1 --port 8000
   ```

2. Check Prometheus metrics are exposed:

   ```bash
   curl -s http://localhost:8000/metrics | head -20
   ```

   ```
   # HELP mcp_hangar_build_info Build and version information for MCP Hangar
   # TYPE mcp_hangar_build_info gauge
   mcp_hangar_build_info{python="...",version="..."} 1
   ...
   # HELP mcp_hangar_mcp_server_state Current mcp_server state (0=cold, 1=initializing, 2=ready, 3=degraded, 4=dead)
   # TYPE mcp_hangar_mcp_server_state gauge
   mcp_hangar_mcp_server_state{mcp_server="my-mcp"} 0
   ```

   A series with labels appears once something has set it: there is no
   `mcp_hangar_tool_calls_total` line until the first tool call.

3. Point your own Prometheus at that endpoint:

   ```yaml
   scrape_configs:
     - job_name: 'mcp-hangar'
       static_configs:
         - targets: ['localhost:8000']
       metrics_path: /metrics
   ```

   Hangar ships no monitoring stack to start. On Kubernetes the chart does the
   wiring for you — `serviceMonitor.enabled=true` and `dashboards.enabled=true`,
   see [Observability → Monitoring Stack](../guides/OBSERVABILITY.md#monitoring-stack).

4. Import a dashboard into your Grafana from
   [`mcp-hangar/files/dashboards/`](https://github.com/mcp-hangar/helm-charts/tree/main/mcp-hangar/files/dashboards)
   (`overview.json` is the one to start with).

5. Make a tool call and watch the metrics update:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp","tool":"add","arguments":{"a":1,"b":2}}]}}}' > /dev/null
   curl -s http://localhost:8000/metrics | grep '^mcp_hangar_tool_calls_total'
   ```

   ```
   mcp_hangar_tool_calls_total{mcp_server="my-mcp",status="success",tool="add"} 1.0
   ```

   The call starts the cold server first, so
   `mcp_hangar_mcp_server_state{mcp_server="my-mcp"}` now reads 2 and
   `mcp_hangar_mcp_server_cold_start_seconds` has its first observation.

## What Just Happened

Hangar exposes Prometheus-format metrics at `/metrics`; scraping them and rendering them is your Prometheus and Grafana's job. The maintained dashboards and alert rules ship with the Helm chart. Key metrics:

| Metric | Type | What it tells you |
| -------- | ------ | ------------------- |
| `mcp_hangar_tool_calls_total` | Counter | Total tool invocations per MCP server, tool and `status` (`success`, `error`) |
| `mcp_hangar_tool_call_duration_seconds` | Histogram | Latency distribution per MCP server/tool |
| `mcp_hangar_mcp_server_state` | Gauge | Current state per MCP server (0=cold, 1=initializing, 2=ready, 3=degraded, 4=dead) |
| `mcp_hangar_mcp_server_cold_start_seconds` | Histogram | Cold start latency per MCP server |
| `mcp_hangar_health_checks_total` | Counter | Health check results per MCP server |
| `mcp_hangar_circuit_breaker_state` | Gauge | Circuit breaker state per group, one series per `state` (1 for the current one). Only groups have a breaker; the group id is in the `mcp_server` label |

## Key Config Reference

No new config keys. Metrics are always available in HTTP mode.

| Endpoint | Description |
| ---------- | ------------- |
| `/metrics` | Prometheus text format |

## What's Next

Metrics tell you what happened. Traces tell you why.

--> [08 -- Observability: Langfuse](08-observability-langfuse.md)
