# Runbook: tracing diagnosis

Use this page to find one request in your trace backend, read why Hangar allowed or refused it, and tell sampling apart from dropped spans and from export that never happened. It describes only behaviour that is shipped and proven by a test. Anything else is listed under [Not yet traced](#not-yet-traced).

How to configure the exporter, who owns the tracer provider, and how logs join traces are covered in [OpenTelemetry integrations](../observability/otel-integrations.md#effective-tracing-configuration).

The span trees and attribute values below were captured from a real `mcp-hangar serve --http` process, run from core `main` at `d9766bd4`. It exported over OTLP/gRPC to an OpenTelemetry Collector 0.96.0 with the file exporter from `examples/otel-collector/`. Retry examples come from the assertions of the core unit tests, not from a capture.

Attribute keys are the constants in core's `observability/conventions.py`, with two groups of exceptions. `error.type`, `exception.type` and the resource keys belong to OpenTelemetry. `hangar.startup.role`, `hangar.startup.mechanism`, `cold_start.result` and the audit record's `mcp.event.name` are exported as shown, but are defined next to the code that writes them rather than in that registry.

## Is anything being exported?

Check the gateway's startup log before you look in a backend. Each line below is logged once, at startup.

| Log event | Meaning |
| --- | --- |
| `tracing_initialized` with `exporters=['otlp_grpc']` | Hangar registered its own provider with that exporter. This does not prove delivery: nothing has contacted the collector yet. |
| `tracing_disabled_by_config` | `MCP_TRACING_ENABLED=false` or `observability.tracing.enabled: false`. No spans at all. |
| `tracing_disabled_otel_not_available` | The OpenTelemetry SDK is not installed. No spans at all. |
| `tracing_otlp_exporter_skipped` with `reason=empty_endpoint` | `OTEL_EXPORTER_OTLP_ENDPOINT` is set to an empty value. No OTLP exporter was added. |
| `tracing_otlp_exporter_unavailable` | `reason=unsupported_protocol` or `reason=package_missing`. No OTLP exporter was added. |
| `tracing_no_exporters_configured` | No exporter was added, so Hangar registered no provider. |
| `tracing_external_provider_in_use` | Another component registered a provider first. Hangar's spans go through that provider, and its exporter settings apply. |
| `tracing_sampler_configured` | The sampler class in use, for example `ParentBased`. |

## Find one request

A `hangar_call` over streamable HTTP produces one trace. This is the warm call from the capture:

```
tools/call hangar_call              SERVER, opened by the mcp SDK
  hangar_call
    hangar_call.validate
    hangar_call.authorize
    batch.execute
      batch.call.add                the call's governance span
        policy.check_access
        approval_gate.check
        concurrency.acquire
        command.send.InvokeToolCommand
          dispatch.InvokeToolCommand
            rate_limit.check
            handler.InvokeToolCommand
              execute_tool add      CLIENT, the upstream call
```

`event.publish.<Type>` and `event_store.append` spans also appear in the same trace. They are omitted here.

Ways to get to the trace:

- **From a log line.** Structured log lines written inside a span carry `trace_id` and `span_id`. The `batch_call_refused` line for a refused call is one of them.
- **From the caller's trace.** If the client sends a valid W3C `traceparent` in the request's `params._meta`, the SDK's SERVER span becomes a child of the caller's span, and the whole request sits in the caller's trace. Without a carrier, the SERVER span is the root of a new trace. Hangar's own propagation reads and writes `traceparent` and `tracestate` only, and it never forwards baggage upstream.
- **By server and tool.** `batch.call.<tool>` carries `mcp.server.id` and `gen_ai.tool.name`. If the bound identity has them, it also carries `mcp.caller.type`, `mcp.caller.tenant_id` and `mcp.correlation_id`. The caller's identifiers (`mcp.caller.id`, `mcp.user.id`, `mcp.agent.id`, `mcp.session.id`) are added only when the operator opts in with `MCP_TRACING_CALLER_IDS=true` or `observability.tracing.caller_ids`; to find one caller's calls without it, use the audit records, which always carry the caller. Unknown values are left out, never exported empty.

Every span shares the resource of the process that emitted it, so `service.instance.id` picks out one replica.

The queries on this page run `jq` over the Collector's file exporter output: one OTLP JSON object per line. The attribute filters carry over to any backend. List the span names of one trace:

```bash
jq -r --arg t "$TRACE_ID" '.resourceSpans[]?.scopeSpans[].spans[]
  | select(.traceId == $t) | "\(.name) kind=\(.kind) status=\(.status.code // 0)"' telemetry.jsonl
```

## Explain a decision

### Gate decisions

`batch.call.<tool>` gets one `hangar.gate.decision` span event for each stage of the batch executor's gate chain that runs. The events are recorded in order and none overwrites another. Each event carries `hangar.gate.name`, `hangar.gate.outcome` (`allow`, `deny`, `skip`, `deferred` or `error`), and, when the gate can say why, a bounded `hangar.gate.reason`. A digest-pin gate also records the pinned digest as `hangar.gate.revision`. The thirteen gate names are, in order: `cancelled_before_execution`, `global_timeout`, `resolve_target`, `tool_access`, `withdrawal`, `digest_pin`, `circuit_breaker`, `validators`, `tenant_budget`, `approval`, `cold_start`, `deferred_digest_pin` and `cancelled_after_cold_start`.

The call's summary is scalar: `hangar.call.outcome` is `allow`, `deny` or `error`. For a refusal, `hangar.refusal.gate` and `hangar.refusal.reason` name the first gate that refused. No gate, cold start or upstream span appears after it. This is the deny from the capture, a tool on the server's `deny_list`:

```
batch.call.power   status UNSET
  mcp.server.id=math  gen_ai.tool.name=power
  hangar.call.outcome=deny  hangar.refusal.gate=tool_access
  hangar.refusal.reason=tool_not_in_access_policy  error.type=ToolAccessDeniedError
  event hangar.gate.decision  name=tool_access  outcome=deny  reason=tool_not_in_access_policy
```

The trace stops at `policy.check_access`: there is no `concurrency.acquire`, no `command.send.InvokeToolCommand` and no `execute_tool` span. The gateway logged the refusal once, at warning, with the same trace ID:

```
batch_call_refused  gate=tool_access  reason=tool_not_in_access_policy
  error_type=ToolAccessDeniedError  mcp_server=math  tool=power  trace_id=... span_id=...
```

List every refused call and the gate that refused it:

```bash
jq -c '.resourceSpans[]?.scopeSpans[].spans[]
  | (.attributes // [] | map({(.key): (.value | to_entries[0].value)}) | add) as $a
  | select($a["hangar.call.outcome"] == "deny")
  | {traceId, name, gate: $a["hangar.refusal.gate"], reason: $a["hangar.refusal.reason"]}' telemetry.jsonl
```

### Refusal versus failure

Since 2.22.0, an expected refusal leaves the Hangar-owned spans UNSET. This covers a gate `deny`, an L7 deny or approval requirement raised at dispatch, and a command-bus rate limit. The refusing exception's class is still recorded as `error.type`. A failure ends ERROR with a bounded `error.type` and an `exception` event that carries only `exception.type`. The status never has a description, and no exception message or stack trace is exported. The core T3 live test asserts this for a tool that fails upstream: `batch.call.divide` is ERROR with `error.type=ToolInvocationError`, and the upstream's error text appears in no exported span.

Count errors on `batch.call.<tool>` or on the `execute_tool <tool>` CLIENT span, not on the SDK's SERVER span. On the flat-tool path, the mcp SDK sets its own SERVER span to ERROR for a `CallToolResult(isError=true)`, even when the call was a governance refusal. Hangar does not own that span and does not change it.

### Dispatch and rate limits

Every command and query dispatched on the buses gets a `dispatch.<Name>` span with `hangar.dispatch.operation`, and `hangar.dispatch.outcome` set to `success`, `rejected` or `error`. A command refused by the rate-limit middleware is `rejected`, and its `rate_limit.check` span stays UNSET. Rate limits are not gates and take no `hangar.gate.*` key.

### Cold start and waiting for a start

The first call to a cold server runs the start inside its own trace:

```
batch.call.add
  mcp_server.cold_start                 cold_start.result=success
    dispatch.StartMcpServerCommand
      rate_limit.check
      handler.StartMcpServerCommand     hangar.startup.role=leader
        mcp_server.launch               mcp.server.mode=subprocess
        initialize
        notifications/initialized
        tools/list
  concurrency.acquire
  command.send.InvokeToolCommand
  ...
```

In the capture, three calls reached a cold server concurrently. One trace has the shape above. The other two recorded `hangar.gate.decision name=cold_start outcome=skip reason=not_cold` and waited in a `mcp_server.startup_wait` span under `handler.InvokeToolCommand`, with `hangar.startup.role=waiter` and `hangar.startup.mechanism=ensure_ready`. A caller that waits in the executor's single flight instead records `hangar.startup.mechanism=single_flight`, and its wait span carries a link to the leader's `mcp_server.cold_start` when the leader published one. A waiter that arrives before that gets no link: Hangar never invents a cause. The launch span, `mcp_server.launch`, is on `main` and unreleased after 2.23.0.

```bash
jq -c '.resourceSpans[]?.scopeSpans[].spans[]
  | select(.name == "mcp_server.cold_start" or .name == "mcp_server.launch" or .name == "mcp_server.startup_wait")
  | {traceId, name, links: (.links // [] | length),
     attributes: (.attributes | map({(.key): (.value | to_entries[0].value)}) | add)}' telemetry.jsonl
```

### Retries

Two layers can retry one call, and both are recorded, since 2.22.0. Each `command.send.InvokeToolCommand` carries its 1-based `hangar.retry.index`. When a retry policy applies, the executor opens `invoke_with_retry` around the attempts. Each retried failure adds a `hangar.retry.attempt` event with `hangar.retry.layer=executor`, `hangar.retry.index`, a bounded `hangar.retry.reason` and `hangar.retry.backoff_s`. `invoke_with_retry` ends with `hangar.retry.outcome`: `success`, `exhausted` (the budget ran out) or `non_retryable` (the first failure was not worth retrying). The HTTP client's resends are `hangar.retry.attempt` events with `hangar.retry.layer=http` on the `execute_tool <tool>` CLIENT span. They are not separate CLIENT spans.

### Background work

These spans are on `main` and unreleased after 2.23.0. They are not children of a tool call:

- `mcp_server.health_check`: one span per check that runs, with `hangar.health.outcome` (`healthy`, `unhealthy` or `error`) and `mcp.health.consecutive_failures`.
- `saga.run`: one span per synchronous saga run, with `hangar.saga.type` and `hangar.saga.outcome`, and one `hangar.saga.step` event per step. A command fired later by a saga timer opens `saga.scheduled_command` in a new trace, linked to the span that scheduled it.
- `event.publish.<Type>`: one span per domain event, with `hangar.event.id`, `hangar.event.producer` and `hangar.event.delivery_mode` (`live`, `tailed` or `recovered`). Each handler run adds a `hangar.event.handled` event with its name, kind and outcome. `event_store.append` carries `hangar.event_store.append.outcome`.

## Not yet traced

Do not build queries or alerts on these. The task that will add each one is named.

| Question | State |
| --- | --- |
| Which group member was selected, and why | Not yet traced (#1286). |
| What an L7 egress policy decided, in which mode, and under which policy revision | Not yet traced (#1295). The refusal itself is visible: the spans stay UNSET and the call's `hangar.call.outcome` is `deny`. |
| Payload mutation, the per-call size limit and batch truncation | Not yet traced (#1298, not merged). |
| Exemplars from metrics to traces, and diagnosis by scenario | Out of scope here (#1305). |

`mcp.server.id` means the logical target the caller named on `batch.call.<tool>`, `policy.check_access`, `approval_gate.check` and `concurrency.acquire`. On `mcp_server.cold_start` and `command.send.InvokeToolCommand`, it is the group member that was selected. For a server that is not in a group, the two are the same. #1286 will change this so that `mcp.server.id` always means the logical target.

## Sampling, dropped spans and missing export

These three look the same in a backend, where the trace is absent. They have different causes and leave different evidence.

| Situation | Cause | Evidence |
| --- | --- | --- |
| **Not sampled** | The sampler decided not to record the trace. The default is `parentbased_always_on`, so a caller's `traceparent` with the sampled flag off turns Hangar's spans off for that request. | No counter moves and no log line is written. Check `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` and the caller's sampled flag. Audit records are still emitted for an unsampled call. |
| **Dropped at export** | The collector was unreachable or rejected the batch. The batch processor drops that batch. | `mcp_hangar_otlp_export_failures_total` increases, and the Helm chart's `MCPHangarTelemetryExportFailing` alert fires on it. Audit records have their own counter, `mcp_hangar_otlp_audit_export_failures_total`. |
| **Dropped at shutdown** | The final flush is bounded to five seconds. | `tracing_shutdown_timed_out` in the log. |
| **Never exported** | Tracing is off, no exporter was built, or another provider owns export. | One of the startup lines in [Is anything being exported?](#is-anything-being-exported). The export-failure counter stays at zero, because nothing tries to export. |

Hangar has no counter for spans dropped because the SDK's in-memory batch queue was full. Tune that queue with the SDK's `OTEL_BSP_*` variables.

## Missing audit records

An OTLP audit record (scope `mcp_hangar.audit`, `mcp.event.name=tool_invocation`) is written for an invoked tool, not for a call that a gate refused. In the capture, the refused call produced a `batch_call_refused` log line and a span, and no `tool_invocation` record. If records are missing for calls that were allowed:

- Check that audit export is on. It needs an OTLP endpoint set explicitly, in `OTEL_EXPORTER_OTLP_ENDPOINT` or `observability.tracing.otlp_endpoint`. `MCP_AUDIT_EXPORT_ENABLED=false` turns it off.
- Check `mcp_hangar_otlp_audit_export_failures_total` and the `audit_log_export_initialized` log line.
- Compare the allowed calls with the audit records that arrived:

```bash
jq -c '.resourceLogs[]?.scopeLogs[] | select(.scope.name == "mcp_hangar.audit") | .logRecords[]
  | {traceId, attributes: (.attributes | map({(.key): (.value | to_entries[0].value)}) | add)}
  | select(.attributes["mcp.event.name"] == "tool_invocation")' telemetry.jsonl
```

## Live-install checklist

Run through this list on a new install before relying on its traces.

1. **Image and versions.** Record the image digest (`kubectl get pod -o jsonpath='{.status.containerStatuses[*].imageID}'`). The image installs the OpenTelemetry packages unpinned at build time, so read the versions in the running container (`pip show opentelemetry-sdk opentelemetry-exporter-otlp`). Every exported span's resource also carries `telemetry.sdk.version`.
2. **Effective settings.** Read the startup lines `tracing_sampler_configured`, `tracing_otlp_exporter_added` (protocol, and whether the endpoint came from Hangar's configuration or from the environment and SDK default) and `tracing_initialized` (the exporters). Hangar does not log endpoints or headers, so compare the environment with the [precedence rules](../observability/otel-integrations.md#effective-tracing-configuration).
3. **Export health.** Check that `mcp_hangar_otlp_export_failures_total` and `mcp_hangar_otlp_audit_export_failures_total` stay flat. Enable the chart's alerts and dashboards (`prometheusRule.enabled`, `dashboards.enabled`) from [mcp-hangar/helm-charts](https://github.com/mcp-hangar/helm-charts/tree/main/mcp-hangar/files) instead of writing your own.
4. **Collector self-telemetry.** Confirm that the Collector's own metrics (port 8888 in the example) show spans and log records being accepted, not refused.
5. **Controlled requests.** Make one warm call and one call to a tool you have denied. Check that the warm trace ends in an `execute_tool <tool>` CLIENT span, that the denied call has `hangar.call.outcome=deny` with no CLIENT span, and that one `tool_invocation` audit record arrived for the warm call.
