# Tool Invocations with hangar_call

Execute one or more tool invocations with a single unified API.

## Overview

The `hangar_call()` tool is the unified API for all tool invocations. Whether you need a single call or parallel batch execution, the format is consistent.

**Key benefits:**

- **Unified API** - One function for single calls and batches
- **Parallel execution** - Multiple calls run concurrently
- **Automatic retry** - Built-in retry with exponential backoff
- **Single-flight cold starts** - Multiple calls to the same COLD MCP server trigger only one startup
- **Partial success handling** - Failed calls don't block successful ones
- **Fail-fast mode** - Optionally abort on first error
- **Circuit breaker integration** - Respects MCP server health status

## Basic Usage

### Single Invocation

```python
# Simple call
hangar_call(calls=[
    {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}}
])

# With retry for reliability
hangar_call(
    calls=[{"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}}],
    max_attempts=3
)
```

### Batch Invocation (Parallel)

```python
# Execute multiple calls in parallel - much faster than sequential
hangar_call(calls=[
    {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}},
    {"mcp_server": "math", "tool": "multiply", "arguments": {"a": 3, "b": 4}},
    {"mcp_server": "fetch", "tool": "get", "arguments": {"url": "https://api.example.com"}},
])
# Total time: max(t1, t2, t3) instead of t1 + t2 + t3
```

## API Reference

### hangar_call

```python
hangar_call(
    calls: list[dict],           # List of invocations to execute
    max_concurrency: int = 10,   # Max parallel invocations (1-50)
    timeout: float = 60.0,       # Global timeout in seconds (1-300)
    fail_fast: bool = False,     # Abort on first error
    max_attempts: int = 1,       # Total attempts per call including retries (1-10)
) -> dict
```

**Parameters:**

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `calls` | `list[dict]` | required | List of call specifications |
| `max_concurrency` | `int` | 10 | Maximum parallel workers (1-50) |
| `timeout` | `float` | 60.0 | Global timeout for entire batch (1-300s) |
| `fail_fast` | `bool` | False | If True, abort remaining calls on first error |
| `max_attempts` | `int` | 1 | Total attempts per call including retries (1-10; the default 1 means no retry unless a `retry:` block is configured) |

**Call specification:**

Each item in `calls` must be a dictionary with:

| Field | Type | Required | Description |
| ------- | ------ | ---------- | ------------- |
| `mcp_server` | `str` | Yes | MCP Server ID |
| `tool` | `str` | Yes | Tool name |
| `arguments` | `dict` | Yes | Tool arguments |
| `timeout` | `float` | No | Per-call timeout (overrides global) |

### Response Schema

```python
{
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",  # UUID for tracing
    "success": True,          # True if ALL calls succeeded
    "total": 3,               # Total number of calls
    "succeeded": 3,           # Number of successful calls
    "failed": 0,              # Number of failed calls
    "elapsed_ms": 1234.5,     # Total batch execution time
    "results": [
        {
            "index": 0,                      # Original position in calls array
            "call_id": "...",                # UUID for per-call tracing
            "success": True,
            "result": {"sum": 3},            # Tool result if success
            "error": None,                   # Error message if failed
            "error_type": None,              # Error classification
            "elapsed_ms": 45.2,              # Individual call duration
            "retry_metadata": {              # Present if max_attempts > 1
                "attempts": 2,
                "retries": ["TimeoutError"],
                "total_time_ms": 1234.5
            }
        },
        # ... more results
    ]
}
```

## Examples

### With Automatic Retry

```python
# Retry on transient failures (recommended for unreliable mcp_servers)
hangar_call(
    calls=[
        {"mcp_server": "fetch", "tool": "get", "arguments": {"url": "https://api.example.com"}}
    ],
    max_attempts=3
)

# Response includes retry metadata:
{
    "results": [{
        "success": True,
        "result": {...},
        "retry_metadata": {
            "attempts": 2,           # Succeeded on 2nd attempt
            "retries": ["TimeoutError"],  # 1st attempt failed with timeout
            "total_time_ms": 1500.0
        }
    }]
}
```

### Mixed MCP servers (Parallel Cold Starts)

When calling multiple COLD MCP servers, they start in parallel:

```python
hangar_call(calls=[
    {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}},
    {"mcp_server": "sqlite", "tool": "query", "arguments": {"sql": "SELECT 1"}},
    {"mcp_server": "fetch", "tool": "get", "arguments": {"url": "https://api.github.com"}},
], max_concurrency=3)
# All 3 mcp_servers start simultaneously if COLD
```

### Fail-Fast Mode

Stop processing on first error:

```python
results = hangar_call(
    calls=[
        {"mcp_server": "math", "tool": "divide", "arguments": {"a": 1, "b": 0}},  # Will fail
        {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}},
        {"mcp_server": "math", "tool": "multiply", "arguments": {"a": 3, "b": 4}},
    ],
    fail_fast=True,
)
# Calls already running when #0 fails finish; calls not yet started come back
# with "error": "Cancelled before execution", "error_type": "CancellationError"
```

`fail_fast` acts on failures at execution time. A call naming an unknown server
or tool fails [validation](#validation) instead, and then no call in the batch
runs at all, with or without `fail_fast`.

### Per-Call Timeouts

Different timeouts for different calls:

```python
hangar_call(calls=[
    {"mcp_server": "fetch", "tool": "get", "arguments": {"url": "..."}, "timeout": 5.0},
    {"mcp_server": "ml", "tool": "predict", "arguments": {...}, "timeout": 30.0},
], timeout=60.0)
# Effective timeout = min(per_call_timeout, remaining_global_timeout)
```

### Circuit Breaker Behavior

If a MCP server's circuit breaker is OPEN, calls to it fail immediately:

```python
results = hangar_call(calls=[
    {"mcp_server": "math", "tool": "add", "arguments": {"a": 1, "b": 2}},
    {"mcp_server": "unhealthy_mcp_server", "tool": "foo", "arguments": {}},  # CB OPEN
])
# Response:
{
    "success": False,  # Partial failure
    "succeeded": 1,
    "failed": 1,
    "results": [
        {"index": 0, "success": True, "result": {"sum": 3}, ...},
        {"index": 1, "success": False, "error": "Circuit breaker open (too many consecutive failures)", "error_type": "CircuitBreakerOpen", ...}
    ]
}
```

## Behavior Details

### Validation

Batch validation is **eager** - the entire batch is validated before any execution:

- MCP Server existence
- Tool existence (for MCP servers with predefined tools)
- `arguments` present and a dictionary (not checked against the tool's schema)
- Batch size limits
- Timeout bounds

If validation fails, no calls are executed:

```python
{
    "success": False,
    "error": "Validation failed",
    "validation_errors": [
        {"index": 0, "field": "mcp_server", "message": "McpServer 'foo' not found"}
    ]
}
```

### Single-Flight Cold Starts

When multiple calls target the same COLD MCP server, the MCP server starts exactly once:

```python
# 5 calls to COLD "math" mcp_server = 1 startup, then 5 parallel tool calls
hangar_call(calls=[
    {"mcp_server": "math", "tool": "add", "arguments": {"a": i, "b": 1}}
    for i in range(5)
])
```

### Retry Behavior

When `max_attempts > 1`:

- Retries use exponential backoff
- A `retry:` block in the configuration sets the attempts, and applies even
  when the caller leaves `max_attempts` at its default of 1. A caller's
  `max_attempts` of 2 or more can lower the configured count, never raise it
  (see [Configuration](../reference/configuration.md#retry))
- Only transient errors trigger retry (timeout, network errors, malformed JSON)
- Permanent errors (validation, MCP server not found) do not retry
- Each call retries independently within the batch

### Timeout Resolution

Effective timeout per call = `min(per_call_timeout, remaining_global_timeout)`

Example:

- Global timeout: 60s
- Per-call timeout: 30s
- Elapsed time: 50s
- Effective timeout: min(30, 10) = 10s

A call held for [approval](APPROVAL_ADAPTERS.md) is not cut short by the batch
timeout: it reads its approval outcome (`approval_timeout` or `approval_denied`;
an approval that arrives after the deadline reads `CancellationError` and is not
dispatched), and the batch returns when the hold ends. A call the budget runs out
on before it is held reads `TimeoutError`.

### Response Size

An upstream response is bounded where it is read. One larger than the limit,
32 MiB by default, is not read: the call fails with `error_type:
"ResponseTooLarge"`, and the next call on the same server is served. Set the
limit with `execution.max_response_bytes`, the `MCP_MAX_RESPONSE_BYTES`
environment variable (which wins), or a server's own `max_response_bytes`.

This replaced, in 2.24.0, a 10MB per-call cap that dropped an oversized result
after reading it and returned `truncated_reason: "response_size_exceeded"`.

A 50MB total-batch ceiling is defined as a constant and **not enforced**:
nothing compares against it. A batch of many large responses is bounded only by
the per-call limit multiplied by the call count.

When response truncation is configured, a result cut to fit the batch budget
carries `truncated: true`, a `truncated_reason`, `original_size_bytes` and a
`continuation_id` for `hangar_fetch_continuation`.

## Limits

| Limit | Value | Behavior |
| ------- | ------- | ---------- |
| Max calls per batch | 100 | Validation error |
| Max concurrency | 50 | Clamped to limit |
| Max timeout | 300s | Clamped to limit |
| Max attempts | 10 | Clamped to limit |
| Max response per call | 32 MiB (configurable) | Call fails with `ResponseTooLarge` |
| Max total response | 50MB | Not enforced |

## Metrics

Prometheus metrics for batch operations:

```
mcp_hangar_batch_calls_total{result="success|partial|failure|validation_error"}
mcp_hangar_batch_size_bucket{}
mcp_hangar_batch_duration_seconds_bucket{}
mcp_hangar_batch_concurrency{}
mcp_hangar_batch_truncations_total{reason="batch_budget"}
mcp_hangar_batch_circuit_breaker_rejections_total{mcp_server="..."}
mcp_hangar_batch_cancellations_total{reason="timeout|fail_fast"}
```

## Configuration

**There is no `batch:` block.** One was documented here and is not read
anywhere -- the batch limits are module constants in `server/tools/batch/`. Writing the block changes nothing, which is worse than
having no knob at all: the operator believes a limit was raised and it was not.

The values in force:

| | |
| --- | --- |
| Calls per batch | 100 |
| Concurrency | 50 global, 10 per server |
| Timeout | 60s default, 300s maximum |
| Response per call | 32 MiB, set with `execution.max_response_bytes` |

Per-call concurrency and the response limit are tunable through `execution:` --
see [Configuration](../reference/configuration.md#execution) -- and retry
attempts through `retry:`.

## Migration from Previous API

If you were using the previous tools, here's how to migrate:

| Old API | New API |
| --------- | --------- |
| `registry_invoke(mcp_server, tool, arguments)` | `hangar_call(calls=[{"mcp_server": ..., "tool": ..., "arguments": ...}])` |
| `registry_invoke_ex(..., max_retries=5)` | `hangar_call(calls=[...], max_attempts=5)` |
| `registry_invoke_stream(...)` | `hangar_call(calls=[...])` (progress logged internally) |
| `hangar_batch(calls=[...])` | `hangar_call(calls=[...])` |

## Best Practices

1. **Use retry for external calls** - Set `max_attempts=3` for fetch, database, and network operations
2. **Group related calls** - Batch calls that can run independently
3. **Set appropriate timeouts** - Use per-call timeouts for varying workloads
4. **Monitor metrics** - Watch `mcp_hangar_batch_duration_seconds` and `mcp_hangar_batch_size`
5. **Handle partial failures** - Check `succeeded` and `failed` counts
6. **Use fail-fast sparingly** - Only when all-or-nothing is required

## Limitations

- **No dependency ordering** - Calls are independent; use sequential calls if you need result of A as input to B
- **No streaming** - Results are returned when all calls complete
