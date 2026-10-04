# 01 — HTTP Gateway

> **Prerequisite:** None
> **You will need:** A running Streamable HTTP MCP server (test server provided below)
> **Time:** 5 minutes
> **Adds:** Single remote MCP server behind Hangar as control plane

## The Problem

You have one MCP server today. Tomorrow you'll have five. You need a control plane before that happens. Right now, Claude Desktop connects directly to your MCP server — no visibility, no lifecycle management, no single point of configuration. When you add the second server, you're managing two configs. By the fifth, it's chaos.

## Prerequisites

You need a running MCP server to point Hangar at. The
[mcp-hangar](https://github.com/mcp-hangar/mcp-hangar) repository ships a test
server in `examples/provider_math/` that runs on Streamable HTTP; run the
commands below from a checkout of it.

```bash
# Build the test MCP server (requires Docker)
docker build -t mcp-math:latest examples/provider_math/

# Start it on port 8080
docker run -d --name mcp-math -p 8080:8080 mcp-math:latest
# The image serves streamable-http on 8080. If you built it before 2.5.0, add
# `-e MCP_TRANSPORT=streamable-http` -- older builds defaulted to stdio and the
# container exited without binding the port.
```

Verify it is running:

```bash
curl -s http://localhost:8080/mcp -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' \
  -H "Content-Type: application/json" | head -c 80
```

You should see an `event: message` line followed by `data:` and the JSON-RPC
response. Keep the container running.

## The Config

```yaml
# config.yaml — Recipe 01: HTTP Gateway
mcp_servers:
  my-mcp:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "My remote MCP server"
    http:
      connect_timeout: 10.0
      read_timeout: 30.0
```

Save this as `~/.config/mcp-hangar/config.yaml`. Every command below passes it
with `--config`, and that is not optional: without `--config`, `serve` reads
`MCP_CONFIG` or `./config.yaml` and never looks in `~/.config/mcp-hangar/`
([mcp-hangar#1657](https://github.com/mcp-hangar/mcp-hangar/issues/1657)).

## Try It

1. Test Hangar with the config (using stdin/stdout)

   ```bash
   echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' | \
     mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve
   ```

   ```json
   {"jsonrpc":"2.0","id":1,"result":{"capabilities":{...},"protocolVersion":"2024-11-05","serverInfo":{"name":"mcp-hangar","version":"..."}}}
   ```

   Hangar responds to MCP initialize, and exits by itself once `echo` closes
   its stdin.

2. Check MCP server status (create test script)

   ```bash
   cat > /tmp/test-hangar.sh << 'EOF'
   #!/bin/bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_status","arguments":{}},"id":2}'
     sleep 2
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>/dev/null | grep '"id":2'
   EOF
   chmod +x /tmp/test-hangar.sh
   /tmp/test-hangar.sh
   ```

   ```json
   {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"...\"id\": \"my-mcp\", \"indicator\": \"[COLD]\", \"state\": \"cold\"..."}]}}
   ```

   MCP Server shows COLD state (not started yet).

3. Ask for the server's tools to trigger the cold start, then list

   ```bash
   cat > /tmp/test-list.sh << 'EOF'
   #!/bin/bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_tools","arguments":{"mcp_server":"my-mcp"}},"id":2}'
     sleep 3
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_list","arguments":{}},"id":3}'
     sleep 2
   ) | mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve 2>/dev/null | grep '"id":3'
   EOF
   chmod +x /tmp/test-list.sh
   /tmp/test-list.sh
   ```

   ```json
   {"jsonrpc":"2.0","id":3,"result":{"content":[{"text":"...\"mcp_server_id\": \"my-mcp\",\n      \"state\": \"ready\",\n      \"mode\": \"remote\",\n      \"alive\": true,\n      \"tools_count\": 5..."}]}}
   ```

   `hangar_list` only reads state: on its own it would still report `cold`.
   `hangar_tools` is what started the server, and it transitioned to READY and
   discovered its tools.

4. Configure Claude Desktop

   Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "hangar": {
         "command": "mcp-hangar",
         "args": ["serve", "--config", "/Users/you/.config/mcp-hangar/config.yaml"]
       }
     }
   }
   ```

   Use an absolute path. Claude Desktop starts the command without a shell, so
   a `~` reaches Hangar unexpanded, and a `--config` path that does not exist
   does not fail: Hangar logs `config_not_found_using_default` and starts on a
   built-in demo configuration instead of yours.

## What Just Happened

Hangar loaded your MCP server configuration and started in stdio mode (JSON-RPC over stdin/stdout). When you sent the `initialize` handshake, Hangar responded with its capabilities. On the `hangar_tools` call, Hangar performed a cold start: it connected to the remote MCP server (`examples/provider_math` in this recipe), sent MCP `initialize` + `tools/list` to discover available tools, and registered them in its internal registry.

The test MCP server doesn't know Hangar exists — it sees standard MCP JSON-RPC requests. This is a transparent proxy pattern. Hangar adds little yet: no group, no circuit breaker, no authentication. The background health check already probes a READY server; recipe 02 looks at it. That's the point — recipe 01 is the baseline.

## Cleanup

When you are done with this recipe (or before starting recipe 02), stop the test container:

```bash
docker rm -f mcp-math
```

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `mode` | string | — | MCP Server mode. Use `remote` for HTTP/SSE MCP servers |
| `endpoint` | string | — | Full URL of the remote MCP server (including path) |
| `description` | string | none | Human-readable description shown in status |
| `http.connect_timeout` | float | `10.0` | TCP connection timeout in seconds |
| `http.read_timeout` | float | `30.0` | Response read timeout in seconds |

## What's Next

Your MCP server is proxied — but what happens when it goes down? Right now, Hangar sends requests into the void and forwards the error. You need visibility into MCP server health before failures surprise you.

→ [02 — Health Checks](02-health-checks.md)
