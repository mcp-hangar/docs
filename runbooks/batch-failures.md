# Runbook: batch high failure rate

**Alert:** `MCPHangarBatchHighFailureRate` (critical) — batch failure ratio exceeds the threshold for 3m.

## What it means

`rate(mcp_hangar_batch_calls_total{result="failure"}) / rate(mcp_hangar_batch_calls_total)`
is above 20% — `hangar_call` batches in which no call succeeded. A batch with some
successes counts as `partial`, not `failure`. A call refused by a gate inside the
executor (tool access, digest pin, circuit breaker, egress policy) counts like a
failed one, so a one-call batch to a tool the access policy denies is a `failure`.

The counter does not see `tool:invoke` authorization denials. They are decided
before the executor runs, so a batch whose every call was denied that way is not
counted at all, and a mixed batch is labelled from the calls that ran. A flood of
unauthorized `hangar_call` batches does not raise this ratio: look for
`AuthorizationDenied` in the batch responses and for `hangar_call_authorization_denied`
in the logs instead.

## Diagnose

```promql
sum by (result) (rate(mcp_hangar_batch_calls_total[5m]))
histogram_quantile(0.95, sum by (le) (rate(mcp_hangar_batch_duration_seconds_bucket[5m])))
sum(rate(mcp_hangar_batch_truncations_total[5m]))         # results cut to the batch response budget?
sum by (reason) (rate(mcp_hangar_batch_cancellations_total[5m]))  # reason: timeout, fail_fast
```

## Remediate

- Truncations high → results larger than the batch's response budget; see whether batches are also large (`MCPHangarBatchSizeTooLarge`) and advise smaller batches.
- Cancellations high → `timeout`: the batch's global timeout or concurrency starvation (`MCPHangarConcurrencyQueueBuildup`); `fail_fast`: one failure stopped the rest of a `fail_fast` batch.
- Refusals → find the refusing gate in the `batch_call_refused` log lines or on the trace ([tracing-diagnosis](tracing-diagnosis.md#gate-decisions)); a caller retrying a denied tool is a policy question, not an outage.
- Failures concentrated on one server → treat as `high-error-rate` for that server.

## Escalate

If batch failures coincide with a circuit breaker (`circuit-breaker`), follow that runbook first.
