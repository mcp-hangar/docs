# WebSockets

MCP Hangar provides a WebSocket endpoint for real-time streaming of domain events.

The endpoint needs a WebSocket library in the gateway's environment, and none is a declared dependency of `mcp-hangar`. Install one beside it (`pip install websockets`, or `wsproto`). Without one, the HTTP server answers the upgrade request with `404` and logs `No supported WebSocket library detected`.

## Endpoint

| Endpoint | Description |
| ---------- | ------------- |
| `/api/ws/events` | All domain events (filterable via subscribe message) |

## Connecting

Use any WebSocket client. Example with `websocat`:

```bash
# Stream all domain events
websocat ws://localhost:8000/api/ws/events
```

## Event Stream (`/api/ws/events`)

Streams all domain events as they occur. Each message is a JSON object:

```json
{
  "event_type": "McpServerStarted",
  "event_id": "ef6b014b-7465-450e-b84c-41e6016bfd7b",
  "occurred_at": 1791137857.2525818,
  "produced_by": "gateway-1-6fabaa87",
  "mcp_server_id": "math",
  "mode": "subprocess",
  "tools_count": 6,
  "startup_duration_ms": 34.6
}
```

Every message carries `event_type`, `event_id`, `occurred_at` (Unix epoch seconds) and `produced_by` (the replica that wrote the event), then the event's own fields.

### Event Types

All domain events are published. Among them:

- `McpServerStateChanged` -- State transition with old/new state.
- `McpServerStarted` -- MCP Server initialization complete.
- `McpServerStopped` -- MCP Server shut down.
- `McpServerDegraded` -- MCP Server marked as degraded.
- `HealthCheckPassed` / `HealthCheckFailed` -- Health check results.
- `ToolInvocationCompleted` / `ToolInvocationFailed` -- Tool call results.
- `McpServerDiscovered` / `McpServerRegistered` / `McpServerDeregistered` -- Discovery events.
- `CircuitBreakerStateChanged` -- Circuit breaker transitions.

### Filtering

After connecting, send a JSON `subscribe` message to filter events:

```json
{
  "type": "subscribe",
  "event_types": ["McpServerStateChanged"],
  "mcp_server_ids": ["math"]
}
```

The server acknowledges with:

```json
{
  "type": "subscribed",
  "event_types": ["McpServerStateChanged"],
  "mcp_server_ids": ["math"]
}
```

The server waits for this first message, up to 5 seconds after accepting the connection, and only then starts streaming: events published before the first message arrives, or before the 5 seconds run out, are not delivered. Only the first `subscribe` is acknowledged.

You can update filters at any time by sending another `subscribe` message; it takes effect without an acknowledgement. Omit a key to not filter on that dimension (e.g., omit `mcp_server_ids` to receive events from all MCP servers). An `event_types` entry matches an event type exactly, and `"*"` matches every type.

## Queue and Backpressure

Each WebSocket connection has an internal message queue (`EventStreamQueue`). If a client falls behind:

1. Messages queue up to 1024 events.
2. Beyond the limit, the oldest queued event is dropped to make room for the new one.
3. The client is not told. The gateway logs a `ws_event_dropped` warning for each dropped event.

## Keep-alive

After 55 seconds without an event, the server sends `{"type": "ping"}`. A client that does not answer with `{"type": "pong"}` within 10 seconds is disconnected.

## Authentication

When auth is enabled, pass credentials via the initial HTTP upgrade headers. The connection needs `audit:read`. A subscriber whose `audit:read` is granted only within a tenant receives only events that name that tenant; the client cannot widen that with a filter.

```bash
websocat "ws://localhost:8000/api/ws/events" -H "X-API-Key: mcp_your_key_here"
```

## Connection Lifecycle

1. Client sends WebSocket upgrade to `/api/ws/events`. A browser `Origin` header must be one of the configured CORS origins, or the upgrade is refused with `403`.
2. Server accepts the connection.
3. (Optional) Client sends a `subscribe` message to set filters.
4. Server streams matching events as JSON messages.
5. Client can send updated `subscribe` messages at any time.
6. On disconnect, the subscription is cleaned up automatically.
