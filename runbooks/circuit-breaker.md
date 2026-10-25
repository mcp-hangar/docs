# Runbook: circuit breaker tripped

**Alert:** `MCPHangarCircuitBreakerTripped` (critical) — `increase(mcp_hangar_batch_circuit_breaker_rejections_total[5m]) > 10` for 2m.

## What it means

Calls are refused with `CircuitBreakerOpen` before they reach the server. That
happens in three cases:

- **READY (2), with failures counted.** The server's consecutive failures
  reached `max_consecutive_failures` (default 3) through failed calls --
  timeouts, connection errors. A failed call raises the count without changing
  the state, so the server still reads READY, no `McpServerDegraded` is
  recorded and the recovery saga does not run. The refusals stop at the next
  passing health check, which resets the count, at most
  `health_check_interval_s` (60 s by default) later. If that check fails too,
  the server degrades.
- **DEGRADED (3).** Its health checks, or its starts, failed
  `max_consecutive_failures` times. The recovery saga restarts it.
- **DEAD (4), inside its backoff.** The refusal says how long to wait. A call
  to a DEAD server after its backoff is not refused: it starts the server.

The counter's `mcp_server` label is the server the call resolved to, the member
for a call to a group.

A group also has its own circuit, which opens on failures across its members.
Its state is `mcp_hangar_group_circuit_open` and
`mcp_hangar_circuit_breaker_state`, and only groups have those series.

## Diagnose

```promql
sum by (mcp_server) (rate(mcp_hangar_batch_circuit_breaker_rejections_total[5m]))
mcp_hangar_mcp_server_state                               # 2 = READY, 3 = DEGRADED, 4 = DEAD
mcp_hangar_circuit_breaker_state{state="open"} == 1       # by group id in mcp_server
```

Find the underlying failure — usually upstream errors or timeouts
(`high-error-rate`, `high-latency`) or failing health checks (`health-failures`)
for the same `mcp_server`.

## Remediate

1. Fix the upstream (restart the server, resolve the timeout/auth issue).
2. A READY server's refusals stop at its next passing health check; nothing
   restarts it, so once the upstream answers again, wait for that check. A
   DEGRADED server is restarted by the recovery saga; once a restart succeeds it
   reads READY (2) and the refusals stop. A DEAD server needs a call after its
   backoff or a deliberate start: work [provider-dead](provider-dead.md).
3. Do NOT keep restarting it while the upstream is still failing — every failed
   start counts against it and ends in DEAD.

## Escalate

If the server keeps cycling between READY and DEGRADED, the upstream is unstable — block it and page its owner.
