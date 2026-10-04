# 08 -- Observability: Langfuse

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar, Langfuse instance (cloud or self-hosted)
> **Time:** 10 minutes
> **Adds:** Distributed tracing for tool invocations via Langfuse

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

observability:                           # NEW: Langfuse tracing
  langfuse:                              # NEW: Langfuse configuration
    enabled: true                        # NEW: enable Langfuse adapter
    public_key: ${LANGFUSE_PUBLIC_KEY}   # NEW: from environment
    secret_key: ${LANGFUSE_SECRET_KEY}   # NEW: from environment
    host: "https://cloud.langfuse.com"   # NEW: Langfuse host
```

## Try It

1. Install the Langfuse SDK with Hangar, and set environment variables:

   ```bash
   pip install "mcp-hangar[langfuse]"
   export LANGFUSE_PUBLIC_KEY="pk-lf-..."
   export LANGFUSE_SECRET_KEY="sk-lf-..."
   ```

2. Start Hangar:

   ```bash
   mcp-hangar serve --config ~/.config/mcp-hangar/config.yaml \
     --http --host 127.0.0.1 --port 8000
   ```

   The log reports `langfuse_initialized` with your host.

3. Make a tool call:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"my-mcp","tool":"add","arguments":{"a":1,"b":2}}]}}}'
   ```

4. Open Langfuse dashboard and find the trace. With Langfuse SDK 4.x it holds:
   - `tools/call hangar_call` -- the MCP request
   - `batch.call.<tool>` -- the call itself, carrying `mcp.server.id`
   - `execute_tool <tool>` -- the call to the upstream
   - `policy.check_access`, `approval_gate.check`,
     `command.send.InvokeToolCommand` -- the gates it passed

   The spans are named after the pipeline that produces them; there is no
   `hangar.` prefix. Which of Hangar's spans reach Langfuse is the SDK's
   choice, not Hangar's: SDK 4.x exports only the spans its default filter
   keeps, so `batch.execute` and `concurrency.acquire` do not appear there
   although Hangar records them.

## What Just Happened

Hangar records every tool call as OpenTelemetry spans. Enabling Langfuse constructs the Langfuse client, and the Langfuse SDK attaches itself to the process's OpenTelemetry tracer provider and sends those spans to `<host>/api/public/otel/v1/traces`. That is where the trace comes from. Hangar's own `LangfuseObservabilityAdapter` is initialised too, but on 2.24.0 nothing calls it, so it records no spans or scores of its own ([mcp-hangar#1683](https://github.com/mcp-hangar/mcp-hangar/issues/1683)).

Calls to an upstream carry a W3C `traceparent` header, so an MCP server that is itself traced with OpenTelemetry joins the same trace.

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `observability.langfuse.enabled` | bool | `false` | Enable Langfuse tracing |
| `observability.langfuse.public_key` | string | -- | Langfuse public key (use env var) |
| `observability.langfuse.secret_key` | string | -- | Langfuse secret key (use env var) |
| `observability.langfuse.host` | string | `https://cloud.langfuse.com` | Langfuse host URL |

`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST`, when set,
take precedence over the file, and `MCP_LANGFUSE_ENABLED` over `enabled`.

## What's Next

You've set up external observability. Now try running MCP servers as local subprocesses instead of remote HTTP.

--> [09 -- Subprocess MCP servers](09-subprocess-mcp-servers.md)
