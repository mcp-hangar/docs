# 06 -- Rate Limiting

> **Prerequisite:** [05 -- Load Balancing](05-load-balancing.md)
> **You will need:** Running Hangar with a load-balanced group from recipe 05
> **Time:** 5 minutes
> **Adds:** Protect MCP servers from request overload

## The Problem

A runaway client sends hundreds of requests per second. Your MCP servers can handle 10 concurrent calls each. Without limits, they queue up, timeout, and cascade into health check failures.

## The Config

```yaml
# config.yaml -- Recipe 06: Rate Limiting
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: "http://localhost:8080"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-backup:
    mode: remote
    endpoint: "http://localhost:8081"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-3:
    mode: remote
    endpoint: "http://localhost:8082"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-group:
    mode: group
    strategy: round_robin
    min_healthy: 1
    members:
      - id: my-mcp
        weight: 1
      - id: my-mcp-backup
        weight: 1
      - id: my-mcp-3
        weight: 1
```

Rate limiting is configured via environment variables:

```bash
export MCP_RATE_LIMIT_RPS=1          # NEW: 1 request per second steady-state
export MCP_RATE_LIMIT_BURST=10       # NEW: allow short bursts up to 10
```

## Try It

Rate limiting guards the MCP tool-call path -- the command bus that every `hangar_call` (and the other `hangar_*` tools) flows through. Exercise it by firing a burst of tool calls in a single session.

1. Configure a tight limit so the burst is easy to hit:

   ```bash
   export MCP_RATE_LIMIT_RPS=1          # 1 request per second steady-state
   export MCP_RATE_LIMIT_BURST=3        # allow a short burst of 3
   ```

2. Fire a burst of `hangar_call`s back-to-back in one session, using the JSON-RPC approach from recipe 05. Print only the responses:

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     for i in $(seq 2 7); do
       echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":'"$i"'}'
     done
     sleep 2
   ) | mcp-hangar serve 2>/dev/null | grep '"id":'
   ```

   The first calls (up to the burst size) return a tool result. Once the burst is exhausted, the command bus rejects the remaining `hangar_call`s with a `RateLimitExceeded` error whose message reads `Rate limit exceeded: ...`:

   ```
   {"jsonrpc":"2.0","id":2,"result": ... "3" ... }
   {"jsonrpc":"2.0","id":3,"result": ... "3" ... }
   {"jsonrpc":"2.0","id":4,"result": ... "3" ... }
   {"jsonrpc":"2.0","id":5,"result": ... "Rate limit exceeded: ..." ... }
   {"jsonrpc":"2.0","id":6,"result": ... "Rate limit exceeded: ..." ... }
   {"jsonrpc":"2.0","id":7,"result": ... "Rate limit exceeded: ..." ... }
   ```

3. Wait for the token bucket to refill, then a fresh call succeeds again:

   ```bash
   sleep 2
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 2
   ) | mcp-hangar serve 2>/dev/null | grep '"id":2'
   ```

   The bucket refills at `MCP_RATE_LIMIT_RPS` tokens per second, so once enough time passes the next call is allowed through.

## What Just Happened

Rate limiting is enforced by a token-bucket limiter wired into the command bus as middleware -- every MCP tool call (`hangar_call` and the other `hangar_*` tools) is dispatched through it. When a call would exceed `MCP_RATE_LIMIT_RPS` (requests per second) and the burst allowance is spent, the middleware raises `RateLimitExceeded` before the command reaches its handler. That error is surfaced back to the MCP client in the tool response. The `MCP_RATE_LIMIT_BURST` setting sizes the bucket, allowing short spikes above the steady-state rate.

Scope: the limiter covers the MCP tool-call (command-bus) path only. The REST `/api/*` routes are **not** rate-limited by these settings -- protecting those endpoints is out of scope for this recipe and handled by separate infrastructure (for example a reverse proxy or gateway in front of Hangar).

## Key Config Reference

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MCP_RATE_LIMIT_RPS` | float | `10` | Requests per second steady-state limit |
| `MCP_RATE_LIMIT_BURST` | int | `20` | Maximum burst above the rate limit |

## What's Next

Congratulations -- you've completed the sequential path. Your setup has health checks, circuit breakers, failover, load balancing, and rate limiting.

The remaining recipes are standalone. Start with [07 -- Observability: Metrics](07-observability-metrics.md) to add Prometheus and Grafana monitoring.
