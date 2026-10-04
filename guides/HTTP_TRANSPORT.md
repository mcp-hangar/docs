# HTTP Transport for Remote MCP servers

MCP Hangar supports connecting to remote MCP servers exposed via HTTP/HTTPS endpoints. This enables integration with MCP servers deployed as standalone HTTP services in production environments.

## Overview

HTTP transport allows MCP Hangar to act as a gateway to remote MCP servers, providing:

- **Unified interface**: Same API for local and remote MCP servers
- **Authentication**: Support for API keys, Bearer tokens, and Basic auth
- **TLS/HTTPS**: Full support for custom CA certificates
- **Connection management**: Automatic retries, timeouts, and connection pooling
- **Observability**: HTTP-specific metrics integrated with existing pipeline

## Configuration

### Basic Remote MCP Server

```yaml
mcp_servers:
  remote-math:
    mode: remote
    endpoint: https://mcp-server.example.com/mcp
    description: "Remote math mcp_server"
```

### Authentication Options

#### No Authentication

```yaml
mcp_servers:
  public-mcp-server:
    mode: remote
    endpoint: http://localhost:8080/mcp
```

#### API Key Authentication

```yaml
mcp_servers:
  api-key-mcp-server:
    mode: remote
    endpoint: https://api.example.com/mcp
    auth:
      type: api_key
      api_key: ${MCP_API_KEY}  # Environment variable
      api_key_header: X-API-Key  # Default header name
```

#### Bearer Token Authentication

```yaml
mcp_servers:
  bearer-mcp-server:
    mode: remote
    endpoint: https://secure.example.com/mcp
    auth:
      type: bearer
      bearer_token: ${MCP_BEARER_TOKEN}
```

#### Basic Authentication

```yaml
mcp_servers:
  basic-auth-mcp-server:
    mode: remote
    endpoint: https://internal.example.com/mcp
    auth:
      type: basic
      username: ${MCP_USERNAME}
      password: ${MCP_PASSWORD}
```

### TLS Configuration

#### Custom CA Certificate

```yaml
mcp_servers:
  private-mcp-server:
    mode: remote
    endpoint: https://private.example.com:8443/mcp
    tls:
      verify_ssl: true
      ca_cert_path: /etc/ssl/certs/internal-ca.pem
```

#### Disable SSL Verification (Development Only!)

```yaml
mcp_servers:
  dev-mcp-server:
    mode: remote
    endpoint: https://dev.example.com/mcp
    tls:
      verify_ssl: false  # WARNING: Only for development!
```

### HTTP Transport Options

```yaml
mcp_servers:
  tuned-mcp-server:
    mode: remote
    endpoint: https://api.example.com/mcp
    http:
      connect_timeout: 10.0  # Connection timeout in seconds
      read_timeout: 60.0     # Read timeout in seconds
      max_retries: 5         # Total attempts, including the first
      retry_backoff_factor: 0.5  # Exponential backoff factor, in seconds
      retry_status_codes: [502, 503, 504]  # Which responses are retried
      headers:               # Additional headers
        X-Request-Source: mcp-hangar
        X-Correlation-Id: ${REQUEST_ID:-default}
```

`max_retries` counts attempts, not extra attempts: `1` disables retrying. A
request is retried when the upstream answers with one of `retry_status_codes`
(default `502`, `503`, `504` -- the codes an ingress returns while an upstream
is rolling) or when the connection cannot be established. Everything else,
including a `500`, comes back to the caller on the first attempt: a retry is
for a failure the upstream is expected to recover from on its own.

The wait between attempts is `retry_backoff_factor * 2^attempt` seconds, so the
default `0.5` waits 0.5s, then 1s, then 2s. A factor of `0` retries without
waiting.

*Before 2.17.1 only connection failures were retried, by the underlying HTTP
library, on a fixed backoff; `retry_backoff_factor` and `retry_status_codes`
were accepted and had no effect.*

## Environment Variable Interpolation

Configuration values support environment variable interpolation using the `${VAR_NAME}` syntax:

- `${VAR_NAME}` - Replace with environment variable value
- `${VAR_NAME:-default}` - Use default value if not set
- `${VAR_NAME:-}` - Allow an empty value, explicitly

This is a property of the whole configuration document, not of the transport
section it is documented in -- `persistence`, `auth`, `observability` and the
rest read the same way. *Before 2.5.0 it applied only inside
`mcp_servers.<id>.auth`, and a `${VAR}` anywhere else arrived as those literal
characters.*

A `${VAR}` that is unset and has no default is **fail-closed**: it refuses
startup rather than substituting an empty string, naming the variable. Since
2.5.0 that refusal covers the whole document, so a key you never had to set
before can now stop a boot. Use `${VAR:-}` where an empty value is intended.

The document is interpolated once, so a value that *contains* a literal
`${...}` -- a generated password, say -- is passed through untouched rather than
being read as another reference.

Example:

```yaml
mcp_servers:
  secure-mcp-server:
    mode: remote
    endpoint: ${MCP_ENDPOINT:-https://localhost:8080/mcp}
    auth:
      type: bearer
      bearer_token: ${MCP_TOKEN}
```

## SSE Streaming Support

HTTP transport supports Server-Sent Events (SSE) for streaming responses from MCP servers. This is automatically detected based on the `Content-Type` header.

When a MCP server responds with `Content-Type: text/event-stream`, the client:

1. Opens an SSE connection
2. Reads events until the response for the request ID is received
3. Handles timeouts gracefully

### Protocol Versions and Sessions

Hangar opens every remote MCP server with `initialize`, and what the upstream
answers decides how the rest of the connection is spoken:

- An upstream that answers `initialize` keeps the version it negotiated. If it returns an `Mcp-Session-Id`, Hangar
  sends that header on every later request, and when the upstream answers a
  request with `404` (the session is gone, typically after an upstream restart)
  Hangar runs `initialize` again and retries the request once.
- A stateless upstream (2026-07-28) answers `initialize` with method-not-found.
  Hangar then carries the protocol version and client info in each request's
  `params._meta`, and never sends or stores a session id.

## Health Checks

Remote MCP servers support the same health check mechanism as local MCP servers:

```yaml
mcp_servers:
  remote-with-health:
    mode: remote
    endpoint: https://api.example.com/mcp
    health_check_interval_s: 30
    max_consecutive_failures: 3
```

Health checks call the MCP `tools/list` method, with a 5-second timeout, on a server that is `ready`. A server that is cold or `dead` is not checked.

## Metrics

HTTP transport exposes the following metrics:

| Metric | Type | Description |
| -------- | ------ | ------------- |
| `mcp_hangar_http_requests_total` | Counter | Total HTTP requests, labeled by mcp_server, method, status_code |
| `mcp_hangar_http_request_duration_seconds` | Histogram | Request latency, labeled by mcp_server, method |
| `mcp_hangar_http_errors_total` | Counter | HTTP errors, labeled by mcp_server and error_type (`http_<status>`, `timeout`, `connection_refused`, `request_failed`, `session_terminated`, `response_too_large`, ...) |
| `mcp_hangar_http_retries_total` | Counter | Retry attempts, labeled by mcp_server and retry_reason (the status code, or `connection_error`) |
| `mcp_hangar_messages_sent_total` | Counter | JSON-RPC messages sent, labeled by mcp_server, method |
| `mcp_hangar_messages_received_total` | Counter | JSON-RPC messages received, labeled by mcp_server, type (response/notification/error) |
| `mcp_hangar_message_size_bytes` | Histogram | Message payload size, labeled by mcp_server, direction (sent/received) |

## Error Handling

### Connection Errors

When a remote MCP server is unavailable:

1. The MCP server transitions to `DEAD` or `DEGRADED` state
2. A `DEGRADED` server is restarted by the recovery saga, with exponential backoff between attempts
3. A `DEAD` server is not health-checked or restarted on its own: the next call or an explicit start brings it back

### Authentication Failures

A 401 or 403 from the upstream fails the call with `HTTP error: 401` (or `403`) and is counted in `mcp_hangar_http_errors_total{error_type="http_401"}`. Failing health checks count toward `max_consecutive_failures`, so a server whose credentials stopped working degrades. Check:

1. Credentials in environment variables
2. Token expiration
3. API key validity

### Timeout Handling

Timeouts are configurable per-MCP server:

- `connect_timeout`: Time to establish connection
- `read_timeout`: Time to receive response

On timeout, the request fails and the MCP server health is affected.

## Security Considerations

1. **Never store secrets in config files** - Use environment variables
2. **Use HTTPS in production** - HTTP is only for local development
3. **Enable SSL verification** - Disable only for development with self-signed certificates
4. **Rotate credentials regularly** - Especially for production environments

## Example: Complete Configuration

```yaml
mcp_servers:
  production-math:
    mode: remote
    endpoint: https://mcp-math.production.example.com/mcp
    description: "Production math service with bearer auth"
    auth:
      type: bearer
      bearer_token: ${MATH_SERVICE_TOKEN}
    tls:
      verify_ssl: true
      ca_cert_path: /etc/ssl/certs/company-ca.pem
    http:
      connect_timeout: 5.0
      read_timeout: 30.0
      max_retries: 3
      headers:
        X-Service-Name: mcp-hangar
        X-Environment: production
    idle_ttl_s: 600
    health_check_interval_s: 30
    max_consecutive_failures: 3
    tools:
      - name: add
        description: Add two numbers
        inputSchema:
          type: object
          properties:
            a: { type: number }
            b: { type: number }
          required: [a, b]
      - name: multiply
        description: Multiply two numbers
        inputSchema:
          type: object
          properties:
            a: { type: number }
            b: { type: number }
          required: [a, b]

logging:
  level: INFO
  json_format: true
```
