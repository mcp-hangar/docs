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
    endpoint: "http://localhost:8080/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-backup:
    mode: remote
    endpoint: "http://localhost:8081/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3

  my-mcp-3:
    mode: remote
    endpoint: "http://localhost:8082/mcp"
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

Rate limiting guards the MCP tool-call path -- the command bus that `hangar_call`, and every other `hangar_*` tool that does work, flows through. Exercise it by firing a burst of tool calls in a single session.

1. Configure a tight limit so the burst is easy to hit:

   ```bash
   export MCP_RATE_LIMIT_RPS=1          # 1 request per second steady-state
   export MCP_RATE_LIMIT_BURST=3        # allow a short burst of 3
   ```

2. Fire a burst of `hangar_call`s back-to-back in one stdio session, as in recipe 01, then one more call two seconds later. Print only the responses:

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     for i in $(seq 2 8); do
       [ "$i" = 8 ] && sleep 2
       echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp-group","tool":"add","arguments":{"a":1,"b":2}}]}},"id":'"$i"'}'
     done
     sleep 3
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>/dev/null | grep '"id":[2-8]'
   ```

   The first calls (up to the burst size) return a tool result. Once the burst is exhausted, the command bus rejects the remaining `hangar_call`s: the call's entry in `results` has `"success": false`, `"error_type": "RateLimitExceeded"` and an `error` that names the budget and when to retry. Responses can arrive out of order:

   ```
   {"jsonrpc":"2.0","id":5,"result": ... "error": "RateLimitExceeded: the rate limit all callers share for InvokeToolCommand is used up (3 at once, refilled at 1 per second). Retry after 0.99s." ... }
   {"jsonrpc":"2.0","id":6,"result": ... "RateLimitExceeded: ..." ... }
   {"jsonrpc":"2.0","id":7,"result": ... "RateLimitExceeded: ..." ... }
   {"jsonrpc":"2.0","id":3,"result": ... "success": true ... "result": 3.0 ... }
   {"jsonrpc":"2.0","id":4,"result": ... "success": true ... "result": 3.0 ... }
   {"jsonrpc":"2.0","id":2,"result": ... "success": true ... "result": 3.0 ... }
   {"jsonrpc":"2.0","id":8,"result": ... "success": true ... "result": 3.0 ... }
   ```

3. Call 8 went through. It was sent two seconds after the burst, and the bucket refills at `MCP_RATE_LIMIT_RPS` tokens per second, so a token was there again.

   Keep the burst and the retry in one session. Each `mcp-hangar ... serve` pipeline is a new Hangar process with a full bucket of its own, so a second pipeline would succeed whether or not anything had refilled.

## What Just Happened

Rate limiting is enforced by a token-bucket limiter wired into the command bus as middleware -- every MCP tool call that does work (`hangar_call`, `hangar_start`, `hangar_tools`, ...) is dispatched through it. The read-only tools (`hangar_list`, `hangar_status`, `hangar_details`, `hangar_group_list` and the like) never are, and are never refused by it. When a call would exceed `MCP_RATE_LIMIT_RPS` (requests per second) and the burst allowance is spent, the middleware raises `RateLimitExceeded` before the command reaches its handler. That error is surfaced back to the MCP client in the tool response, as the failed call's `error` and `error_type`. The `MCP_RATE_LIMIT_BURST` setting sizes the bucket, allowing short spikes above the steady-state rate.

Scope: the limiter sits on the command bus, not on a transport. A REST route that sends a command spends the same bucket: once it is empty, `POST /api/mcp_servers/my-mcp/start` is refused with HTTP 429 and a `RateLimitExceeded` error body. REST routes that only read (`GET`) go through the query bus and are not limited by these settings. Protecting the REST API as a whole is out of scope for this recipe and handled by separate infrastructure (for example a reverse proxy or gateway in front of Hangar).

**The bucket is per process, so the number multiplies by your replica count.**
Three replicas configured for 10 rps admit 30 across the fleet, because each
holds its own bucket. That is deliberate -- a shared bucket puts a database
round trip on the path of every call -- and it means the figure you set here is
per pod, not per gateway. Dividing by the replica count drifts exactly when it
matters, since a rolling update runs N+1 and a failure runs N-1; a fleet-wide
cap belongs at the ingress, where the fleet has one entrance. `GET /api/system/`
reports `system.rate_limits_are_per_instance` so the scope is readable from outside.
See [25 -- Running More Than One Replica](25-multiple-replicas.md).

## Key Config Reference

| Environment Variable | Type | Default | Description |
| --------------------- | ------ | --------- | ------------- |
| `MCP_RATE_LIMIT_RPS` | float | `10` | Requests per second steady-state limit |
| `MCP_RATE_LIMIT_BURST` | int | `20` | Maximum burst above the rate limit |

## What's Next

Congratulations -- you've completed the sequential path. Your setup has health checks, circuit breakers, failover, load balancing, and rate limiting.

The remaining recipes are standalone. Start with [07 -- Observability: Metrics](07-observability-metrics.md) to add Prometheus and Grafana monitoring.
