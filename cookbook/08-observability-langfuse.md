# 08 -- Observability: Langfuse

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar, Langfuse instance (cloud or self-hosted)
> **Time:** 10 minutes
> **Adds:** Distributed tracing for tool invocations in Langfuse, over OTLP

## The Problem

You know a tool call was slow. You don't know whether the delay was in Hangar (routing, cold start) or in the MCP server itself. You need end-to-end traces that break down each phase.

## The Config

```yaml
# config.yaml -- Recipe 08: Langfuse Tracing
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: "http://localhost:8080/mcp"
    health_check_interval_s: 10
    max_consecutive_failures: 3
```

Nothing in `config.yaml` is Langfuse-specific. Langfuse accepts OpenTelemetry
traces over OTLP/HTTP, so it is configured with the standard OpenTelemetry
exporter variables, like any other OTLP backend.

## Try It

1. Install Hangar with the OpenTelemetry extra, and point the trace exporter
   at Langfuse:

   ```bash
   pip install "mcp-hangar[opentelemetry]"
   export LANGFUSE_PUBLIC_KEY="pk-lf-..."
   export LANGFUSE_SECRET_KEY="sk-lf-..."
   AUTH_STRING=$(printf '%s' "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64 | tr -d '\n')

   export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces  # NEW
   export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf                                          # NEW
   export OTEL_EXPORTER_OTLP_TRACES_HEADERS="Authorization=Basic%20${AUTH_STRING},x-langfuse-ingestion-version=4"  # NEW
   ```

   Langfuse takes OTLP over HTTP only, not gRPC, so the protocol matters as
   much as the endpoint. A self-hosted Langfuse is
   `https://<your-host>/api/public/otel/v1/traces`. Use the `TRACES_`
   variables, not `OTEL_EXPORTER_OTLP_ENDPOINT`: the generic one also turns on
   Hangar's OTLP audit log export, which Langfuse does not accept.

2. Start Hangar:

   ```bash
   mcp-hangar serve --config ~/.config/mcp-hangar/config.yaml \
     --http --host 127.0.0.1 --port 8000
   ```

3. Make a tool call:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp","tool":"add","arguments":{"a":1,"b":2}}]}}}'
   ```

4. Open the Langfuse dashboard and find the trace. Its spans include:
   - `tools/call hangar_call` -- the MCP request
   - `batch.call.<tool>` -- the call itself, carrying `mcp.server.id`
   - `execute_tool <tool>` -- the call to the upstream
   - `policy.check_access`, `approval_gate.check`,
     `command.send.InvokeToolCommand` -- the gates it passed

   The spans are named after the pipeline that produces them; there is no
   `hangar.` prefix.

## What Just Happened

Hangar records every tool call as OpenTelemetry spans, and its OTLP exporter
sends them to Langfuse's OTLP endpoint. Langfuse receives what any OTLP backend
receives: names, ids, outcomes and durations, and the trace context propagated
from the caller. Tool arguments and results are not on spans; caller user,
agent and session ids are only when `observability.tracing.caller_ids` is on.
To redact what spans do carry, or to send to Langfuse and another backend, put
an OpenTelemetry Collector in between, with Langfuse as an `otlphttp` exporter.

Calls to an upstream carry a W3C `traceparent` header, so an MCP server that is itself traced with OpenTelemetry joins the same trace.

Before 2.25.0 this recipe enabled Hangar's Langfuse adapter with an
`observability.langfuse` block, `MCP_LANGFUSE_ENABLED` and the `langfuse`
extra. Nothing called that adapter after 2.22.0, and 2.25.0 removes it and its
settings
([mcp-hangar#1683](https://github.com/mcp-hangar/mcp-hangar/issues/1683)): a
leftover scrub setting refuses the boot, and the rest are named in a warning.
Delete them and use the variables above.

## Key Config Reference

| Variable | Value | Description |
| ----- | ------ | ------------- |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `https://cloud.langfuse.com/api/public/otel/v1/traces` | Langfuse's OTLP traces endpoint |
| `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` | `http/protobuf` | Langfuse does not accept gRPC |
| `OTEL_EXPORTER_OTLP_TRACES_HEADERS` | `Authorization=Basic%20<base64 of public_key:secret_key>,x-langfuse-ingestion-version=4` | The `%20` is the space in `Basic <credential>` |

The full recipe, with other regions, is
[`examples/langfuse/README.md`](https://github.com/mcp-hangar/mcp-hangar/blob/main/examples/langfuse/README.md)
in the core repository.

## What's Next

You've set up external observability. Now try running MCP servers as local subprocesses instead of remote HTTP.

--> [09 -- Subprocess MCP servers](09-subprocess-mcp-servers.md)
