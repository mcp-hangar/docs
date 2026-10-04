# 09 -- Subprocess MCP servers

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar, Python 3.11+
> **Time:** 5 minutes
> **Adds:** Run MCP servers as local subprocesses via stdin/stdout

## The Problem

You have a Python MCP server package. You don't want to run it as a separate HTTP service -- you want Hangar to manage its lifecycle directly. Start it on demand, stop it when idle.

## The Config

```yaml
# config.yaml -- Recipe 09: Subprocess MCP servers
mcp_servers:
  math:
    mode: subprocess                     # NEW: subprocess mode
    command: [python, -m, math_server]   # NEW: command to run
    idle_ttl_s: 300                      # NEW: stop after 5min idle
    health_check_interval_s: 60          # stored, but in 2.24.0 the worker checks every 60 s regardless
    max_consecutive_failures: 3
    env:                                 # NEW: environment variables
      PYTHONUNBUFFERED: "1"
```

## Try It

`math_server` stands for your own package. To follow along without one, copy
`examples/provider_math/server.py` from the mcp-hangar repository to
`math_server.py` in the directory you start Hangar from; it speaks stdio by
default and serves `add`, `subtract`, `multiply`, `divide` and `power`.

1. Start Hangar:

   ```bash
   mcp-hangar serve
   ```

2. Check status -- MCP server is COLD (not yet started):

   ```bash
   mcp-hangar status
   ```

   ```
   ╭─────┬────────────┬───────┬────────┬───────╮
   │     │ MCP server │ State │ Health │ Tools │
   ├─────┼────────────┼───────┼────────┼───────┤
   │ --  │ math       │ COLD  │      - │     - │
   ╰─────┴────────────┴───────┴────────┴───────╯
   ```

   In 2.24.0 `mcp-hangar status` cannot reach a running gateway: it probes
   `/health` on ports 8000 and 8080, a route that no longer exists, and falls
   back to reading `config.yaml`. It therefore always reports `COLD` and
   "Server not running". The steps below read state from the gateway itself
   with the `hangar_status` tool.

3. Invoke a tool -- this triggers a cold start. Use the JSON-RPC protocol
   via stdio:

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"math","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 2
   ) | mcp-hangar serve 2>/dev/null | grep '"id":2'
   ```

   ```
   {"jsonrpc":"2.0","id":2,"result":{"content":[...],"isError":false,"structuredContent":{"batch_id":"...","success":true,"total":1,"succeeded":1,"failed":0,"elapsed_ms":408.74,"results":[{"index":0,"call_id":"...","success":true,"result":{"content":[{"text":"{\n  \"result\": 3.0\n}","type":"text"}],"isError":false},"error":null,"error_type":null,"elapsed_ms":401.64}]}}}
   ```

   `hangar_call` answers with a batch envelope: one entry in `results` per call,
   and the server's own answer (`{"result": 3.0}` from the example math server)
   inside it.

4. Watch the state change and the idle stop. Each piped `serve` is its own
   gateway process, so this happens within one session. With `idle_ttl_s: 10`
   for testing:

   ```bash
   (
     echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
     sleep 0.5
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_call","arguments":{"calls":[{"mcp_server":"math","tool":"add","arguments":{"a":1,"b":2}}]}},"id":2}'
     sleep 2
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_status","arguments":{}},"id":3}'
     sleep 45
     echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"hangar_status","arguments":{}},"id":4}'
     sleep 1
   ) | mcp-hangar serve 2>/dev/null | grep -o '"state\\": \\"[a-z]*'
   ```

   ```
   "state\": \"ready
   "state\": \"cold
   ```

   The stop is not instant: the idle sweep runs every 30 seconds, so a server
   stops between `idle_ttl_s` and `idle_ttl_s` + 30 s after its last call. The
   log line is `mcp_server_idle_shutdown`.

## What Just Happened

Subprocess MCP servers communicate via JSON-RPC over stdin/stdout. Hangar starts the process on first tool call, keeps it running while active, and stops it after the idle TTL expires. The `StdioClient` manages message correlation, timeouts, and process lifecycle.

Stderr output is captured into a ring buffer and available via the [Log Streaming](../guides/LOG_STREAMING.md) API.

## One Gateway Only

`subprocess` does not describe a server the gateway talks to; it describes one
the gateway **runs**, as a child process with its stdio attached. There is no
address a peer could use, so a second Hangar replica cannot reach this server --
it would start its own copy, with its own working directory and its own
environment.

*Since 2.5.0*, that is refused rather than allowed to happen quietly:
registering a `subprocess` or `docker` server through the API in a deployment
whose replicas share storage returns **422**, and starting one on a replica that
does not hold the management lease returns **409**. Servers declared in
`config.yaml` still start on the holder.

If you need several replicas to serve the same server, run it as a service and
use `mode: remote`. See
[25 -- Running More Than One Replica](25-multiple-replicas.md).

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `mode` | string | -- | Set to `subprocess` |
| `command` | list[string] | -- | Command and arguments to start the MCP server |
| `idle_ttl_s` | int | `300` | Seconds of inactivity before auto-stop |
| `env` | dict | `{}` | Environment variables for the subprocess |

## What's Next

Subprocesses are great for development. For isolation in production, run MCP servers in containers.

--> [10 -- Discovery: Docker](10-discovery-docker.md)
