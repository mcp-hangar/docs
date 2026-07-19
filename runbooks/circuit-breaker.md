# Runbook: circuit breaker tripped

**Alert:** `MCPHangarCircuitBreakerTripped` (critical) — `increase(mcp_hangar_batch_circuit_breaker_rejections_total[5m]) > 10`.

## What it means

The per-server circuit breaker opened after repeated failures and is now rejecting
calls fast to protect the system. Calls to that server are short-circuited.

## Diagnose

```promql
mcp_hangar_circuit_breaker_state                          # 1 = open, by mcp_server, state
sum by (mcp_server) (rate(mcp_hangar_batch_circuit_breaker_rejections_total[5m]))
```

Find the underlying failure that opened it — usually upstream errors or timeouts
(`high-error-rate`, `high-latency`) for the same `mcp_server`.

## Remediate

1. Fix the upstream (restart the server, resolve the timeout/auth issue).
2. The breaker half-opens automatically and closes on success — watch `mcp_hangar_circuit_breaker_state` return to 0.
3. Do NOT force it closed while the upstream is still failing — it will re-open and amplify load.

## Escalate

If the breaker flaps repeatedly, the upstream is unstable — quarantine or block it and page its owner.
