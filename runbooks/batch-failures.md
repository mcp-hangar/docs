# Runbook: batch high failure rate

**Alert:** `MCPHangarBatchHighFailureRate` (critical) — batch failure ratio exceeds the threshold for 3m.

## What it means

`rate(mcp_hangar_batch_calls_total{result="failure"}) / rate(mcp_hangar_batch_calls_total)`
is high — batched multi-tool requests are failing as a whole.

## Diagnose

```promql
sum by (result) (rate(mcp_hangar_batch_calls_total[5m]))
histogram_quantile(0.95, sum by (le) (rate(mcp_hangar_batch_duration_seconds_bucket[5m])))
sum(rate(mcp_hangar_batch_truncations_total[5m]))         # oversized batches?
sum(rate(mcp_hangar_batch_cancellations_total[5m]))       # cancelled / timed out?
```

## Remediate

- Truncations high → clients sending oversized batches (`MCPHangarBatchSizeTooLarge`); advise smaller batches or raise the limit.
- Cancellations high → per-call timeouts or concurrency starvation (`MCPHangarConcurrencyQueueBuildup`).
- Failures concentrated on one server → treat as `high-error-rate` for that server.

## Escalate

If batch failures coincide with a circuit breaker (`circuit-breaker`), follow that runbook first.
