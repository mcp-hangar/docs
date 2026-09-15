<!-- markdownlint-disable MD046 -->

# Facade API

Programmatic Python interface to MCP Hangar for embedding MCP server management in applications and services.

## Quick Start

=== "Async"

    ```python
    from mcp_hangar import Hangar

    async with Hangar.from_config("config.yaml") as hangar:
        result = await hangar.invoke("math", "add", {"a": 1, "b": 2})
        print(result)
    ```

=== "Sync"

    ```python
    from mcp_hangar import SyncHangar

    with SyncHangar.from_config("config.yaml") as hangar:
        result = hangar.invoke("math", "add", {"a": 1, "b": 2})
        print(result)
    ```

## Creating a Hangar Instance

Three ways to create a Hangar instance:

### From YAML Config File

Load MCP server definitions from a `config.yaml` file:

=== "Async"

    ```python
    hangar = Hangar.from_config("config.yaml")
    ```

=== "Sync"

    ```python
    hangar = SyncHangar.from_config("config.yaml")
    ```

### From Builder (Programmatic)

Use the `HangarConfig` builder to define MCP servers in code:

=== "Async"

    ```python
    from mcp_hangar import Hangar, HangarConfig

    config = (
        HangarConfig()
        .add_mcp_server("math", mode="subprocess", command=["python", "-m", "math_server"])
        .add_mcp_server("fetch", mode="remote", url="https://fetch.example.com/mcp")
        .max_concurrency(30)
        .build()
    )

    hangar = Hangar.from_builder(config)
    ```

=== "Sync"

    ```python
    from mcp_hangar import SyncHangar, HangarConfig

    config = (
        HangarConfig()
        .add_mcp_server("math", mode="subprocess", command=["python", "-m", "math_server"])
        .add_mcp_server("fetch", mode="remote", url="https://fetch.example.com/mcp")
        .max_concurrency(30)
        .build()
    )

    hangar = SyncHangar.from_builder(config)
    ```

### Direct Constructor

Pass a config path or pre-built config data directly:

```python
hangar = Hangar(config_path="config.yaml")
# or
hangar = Hangar(config=config_data)
```

## HangarConfig Builder

The `HangarConfig` builder provides a fluent API for programmatic configuration. Once `.build()` is called, the config is frozen and cannot be modified.

### Builder Methods

| Method | Returns | Description |
| -------- | --------- | ------------- |
| `HangarConfig()` | `HangarConfig` | Create an empty config builder |
| `.add_mcp_server(name, ...)` | `self` | Add a MCP server definition |
| `.enable_discovery(...)` | `self` | Enable discovery sources |
| `.max_concurrency(value)` | `self` | Set the size of the facade's thread pool |
| `.set_intervals(...)` | raises | Refused: always raises `ConfigurationError` |
| `.build()` | `HangarConfigData` | Build and validate the configuration |
| `.to_dict()` | `dict` | Convert to YAML-compatible dict format |

### `.add_mcp_server()` Parameters

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `name` | `str` | required | Unique MCP server identifier |
| `mode` | `str` | `"subprocess"` | MCP Server mode: `subprocess`, `docker`, or `remote` |
| `command` | `list[str] \| None` | `None` | Command for subprocess mode (required for subprocess) |
| `image` | `str \| None` | `None` | Docker image for docker mode (required for docker) |
| `url` | `str \| None` | `None` | HTTP endpoint for remote mode (required for remote) |
| `env` | `dict \| None` | `None` | Environment variables for the MCP server process |
| `idle_ttl_s` | `int` | `300` | Seconds before auto-shutdown when idle |

### `.enable_discovery()` Parameters

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `docker` | `bool` | `False` | Enable Docker label discovery |
| `kubernetes` | `bool` | `False` | Enable Kubernetes annotation discovery |
| `filesystem` | `list[str] \| None` | `None` | Filesystem paths to scan for MCP server YAML files |

### `.max_concurrency()` Parameter

| Parameter | Type | Default | Range | Description |
| ----------- | ------ | --------- | ------- | ------------- |
| `value` | `int` | `20` | 1-100 | Size of the thread pool that runs `invoke()` calls, `stop()` and `health()` |

### `.set_intervals()`

`.set_intervals()` always raises `ConfigurationError`. The gateway reads no GC or health-check interval from its configuration: the workers run on fixed intervals, listed under [Background workers](#background-workers). Remove the call.

### Complete Builder Example

```python
from mcp_hangar import HangarConfig

config = (
    HangarConfig()
    .add_mcp_server(
        "math",
        mode="subprocess",
        command=["python", "-m", "math_server"],
        idle_ttl_s=600,
    )
    .add_mcp_server(
        "llm",
        mode="remote",
        url="https://llm-api.example.com/mcp",
        env={"API_KEY": "${LLM_API_KEY}"},
    )
    .add_mcp_server(
        "sandbox",
        mode="docker",
        image="mcp-sandbox:latest",
    )
    .enable_discovery(docker=True, filesystem=["/etc/mcp/mcp_servers/"])
    .max_concurrency(50)
    .build()
)
```

!!! warning
    Calling `.build()` freezes the configuration. Subsequent calls to `.add_mcp_server()` or other builder methods raise `ConfigurationError`. Calling `.build()` again also raises `ConfigurationError`.

Validation errors (empty MCP server name, invalid mode, missing mode-specific parameters) raise `ConfigurationError` with a descriptive message.

## API Reference

### Lifecycle

=== "Async (Hangar)"

    ```python
    # Start -- bootstraps mcp_servers and background workers
    await hangar.start()

    # Stop -- stops all mcp_servers and workers
    await hangar.stop()

    # Context manager (recommended) -- auto-calls start/stop
    async with Hangar.from_config("config.yaml") as hangar:
        ...
    ```

=== "Sync (SyncHangar)"

    ```python
    # Start
    hangar.start()

    # Stop
    hangar.stop()

    # Context manager (recommended)
    with SyncHangar.from_config("config.yaml") as hangar:
        ...
    ```

`start()` starts what `mcp-hangar serve` starts: the background workers, discovery when it is configured, and, depending on the configuration, coordination and the front-door warm-up.

#### Background workers

- The GC worker runs every 30 seconds and stops a server idle for longer than its `idle_ttl_s`. `.add_mcp_server()` defaults `idle_ttl_s` to 300. The next call starts the server again and pays its start-up time. To keep a server running for the life of the host, give it a larger `idle_ttl_s`, up to 86400.
- The health-check worker checks every running server every 60 seconds, so a failing server is noticed, and one that recovers is returned to rotation, without a call.
- The metrics snapshot worker records metrics history under `./data`, as it does under `serve`.
- A facade created from a config file, with `Hangar.from_config()` or `SyncHangar.from_config()`, watches that file, and a change to it reloads the configuration. To keep the file from being reloaded, set:

    ```yaml
    config_reload:
      enabled: false
    ```

#### Coordination and front-door warm-up

- Under a `coordination:` block, `start()` starts the management lease keeper and the event tailer. The facade takes and renews the management lease, and follows the shared event log, as a served replica does.
- In front-door mode (`tool_access.mode: front_door`), `start()` warms the catalogue. Every configured server is started on a thread of its own, so `start()` does not wait for it. With `tool_access.required_catalogue` set, the required-catalogue retry runs after it.

In egress mode, and without a `coordination:` block, neither runs.

#### Stopping and concurrent starts

`stop()` stops the warm-up and the required-catalogue retry, discovery, the event tailer, all MCP servers and the background workers, then releases the management lease. It waits for the workers' threads to end, up to 10 seconds in total, and up to 10 seconds for a warm-up that is still starting servers.

A second `start()` while started does nothing, and a second `stop()` does nothing. Concurrent `start()` calls share one bootstrap: the later calls return once the first has finished. A `stop()` made while a `start()` is in flight waits for it, then stops everything it started. `SyncHangar.start()` and `SyncHangar.stop()` are serialised across threads in the same way.

### Invocation

=== "Async (Hangar)"

    ```python
    result = await hangar.invoke(
        mcp_server_name="math",
        tool_name="add",
        arguments={"a": 1, "b": 2},
        timeout_s=30.0,  # default: 30.0
        principal=caller,  # default: an anonymous caller
    )
    ```

=== "Sync (SyncHangar)"

    ```python
    result = hangar.invoke(
        mcp_server_name="math",
        tool_name="add",
        arguments={"a": 1, "b": 2},
        timeout_s=30.0,
        principal=caller,
    )
    ```

| Parameter | Type | Default | Description |
| ----------- | ------ | --------- | ------------- |
| `mcp_server_name` | `str` | required | MCP server or group to invoke |
| `tool_name` | `str` | required | Tool name on the MCP server |
| `arguments` | `dict \| None` | `None` | Tool arguments |
| `timeout_s` | `float` | `30.0` | Invocation timeout in seconds, keyword-only |
| `principal` | `Principal \| None` | `None` | The caller, keyword-only. Without one, the call is an anonymous caller's. See [Calling as a principal](#calling-as-a-principal) |

`invoke` runs each call through the same executor as `hangar_call`, so every call-time control your configuration sets applies to it: tool access and withdrawals, digest pins, validators and interceptors, approval, the global and per-server concurrency limits, and tenant budgets.

- Cold MCP servers are auto-started on first invocation.
- `invoke` accepts a group id, as `hangar_call` does, and the call goes to the member the group selects.
- `timeout_s` bounds the wait. The call itself is given `timeout_s` clamped to 1-300 seconds, as `hangar_call` clamps its `timeout`.
- The result is returned whole. The per-call size limit (10 MB) and a `truncation:` section cut `hangar_call` results, not the results `invoke` returns, and no continuation is stored for an `invoke` call.
- A facade call writes the `hangar_call` span and log lines, and is counted in the batch metrics.
- A call through `invoke` has no session and no request headers. Session suspension does not apply to it, and an L7 rule that selects on `Mcp-Param-*` does not fire, as for `hangar_call` over stdio.

!!! note
    Governed `invoke`, `principal=` and `ToolCallFailedError`, and the background workers, coordination and warm-up that `start()` runs, ship in the first release after 2.20.0. For what changes for existing code, see the [Upgrade Guide](../upgrade.md) and core's [`UPGRADE.md`](https://github.com/mcp-hangar/mcp-hangar/blob/main/UPGRADE.md).

#### Calling as a principal

Pass the caller as `principal=`. The call is authorized for `tool:invoke` as an authenticated `hangar_call` caller is, by the roles your configuration gives that principal id and its groups. The principal's `tenant_id` is the tenant the per-tenant controls are applied for.

```python
from mcp_hangar import Hangar
from mcp_hangar.domain.value_objects import Principal, PrincipalId, PrincipalType

caller = Principal(
    id=PrincipalId("agent-1"),
    type=PrincipalType.SERVICE_ACCOUNT,
    tenant_id="team-a",
)

async with Hangar.from_config("config.yaml") as hangar:
    result = await hangar.invoke("math", "add", {"a": 1, "b": 2}, principal=caller)
```

`SyncHangar.invoke` takes the same `principal=`.

Nothing verifies the principal: your application vouches for its id, groups and tenant, as an authenticator does for a request. `Principal.system()` is refused with `ValueError`.

Without a principal, the call is an anonymous caller's, the same as an unauthenticated `hangar_call`:

- With authentication configured, it is refused with the code `AuthorizationDenied`.
- It carries no tenant. With `execution.tenant_limits` set, it shares the budget of callers with no tenant, built from the `"*"` entry, and is refused with `TenantQuotaExceeded` when there is no `"*"` entry.

There is no way to make an unchecked call. If your configuration refuses anonymous callers, pass a principal.

#### Tools that need approval

- `invoke` raises `TimeoutError` at `timeout_s`, and the event loop is not blocked while the call waits. `SyncHangar.invoke` blocks the calling thread for up to `timeout_s`.
- The call holds one of the facade's pool threads until the approval is decided or expires (`approval_timeout_seconds`, 300 seconds by default), even after `invoke` has raised `TimeoutError`. An approval given after `invoke` timed out is refused, so the tool does not run.
- The same pool runs `stop()` and `health()`, and each pending approval takes one of its threads. Size it with `HangarConfig().max_concurrency(...)` for the approvals that can be pending at once.

### MCP Server Management

=== "Async (Hangar)"

    ```python
    # Start a specific mcp_server
    await hangar.start_mcp_server("math")

    # Stop a specific mcp_server
    await hangar.stop_mcp_server("math")

    # Get mcp_server state snapshot
    info: McpServerInfo = await hangar.get_mcp_server("math")

    # List all mcp_servers
    mcp_servers: list[McpServerInfo] = await hangar.list_mcp_servers()
    ```

=== "Sync (SyncHangar)"

    ```python
    hangar.start_mcp_server("math")
    hangar.stop_mcp_server("math")
    info: McpServerInfo = hangar.get_mcp_server("math")
    mcp_servers: list[McpServerInfo] = hangar.list_mcp_servers()
    ```

### Health

=== "Async (Hangar)"

    ```python
    # Health summary for all mcp_servers
    summary: HealthSummary = await hangar.health()

    # Health check for a specific mcp_server
    is_healthy: bool = await hangar.health_check("math")
    ```

=== "Sync (SyncHangar)"

    ```python
    summary: HealthSummary = hangar.health()
    is_healthy: bool = hangar.health_check("math")
    ```

## Data Classes

### McpServerInfo

Frozen dataclass representing a MCP server state snapshot.

| Field | Type | Description |
| ------- | ------ | ------------- |
| `name` | `str` | MCP Server name |
| `state` | `str` | Current state: `cold`, `ready`, `degraded`, `dead` |
| `mode` | `str` | MCP Server mode: `subprocess`, `docker`, `remote` |
| `tools` | `list[str]` | Available tool names |
| `last_used` | `float \| None` | Last invocation timestamp (epoch seconds) |
| `error` | `str \| None` | Error message if MCP server is in error state |

| Property | Type | Description |
| ---------- | ------ | ------------- |
| `is_ready` | `bool` | `True` if `state == "ready"` |
| `is_cold` | `bool` | `True` if `state == "cold"` |

### HealthSummary

Frozen dataclass with aggregate health information.

| Field | Type | Description |
| ------- | ------ | ------------- |
| `mcp_servers` | `dict[str, str]` | Mapping of MCP server name to state |
| `ready_count` | `int` | Number of MCP servers in `ready` state |
| `total_count` | `int` | Total number of MCP servers |

| Property | Type | Description |
| ---------- | ------ | ------------- |
| `all_ready` | `bool` | `True` if all MCP servers are ready |
| `any_ready` | `bool` | `True` if at least one MCP server is ready |

### HangarConfigData

Dataclass holding the built configuration.

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `mcp_servers` | `dict[str, dict]` | `{}` | MCP Server definitions |
| `discovery` | `DiscoverySpec` | default | Discovery configuration |
| `max_concurrency` | `int` | `20` | Thread pool size |

### DiscoverySpec

Dataclass for discovery source configuration.

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `docker` | `bool` | `False` | Enable Docker discovery |
| `kubernetes` | `bool` | `False` | Enable Kubernetes discovery |
| `filesystem` | `list[str]` | `[]` | Filesystem paths to scan |

## Framework Integration

### FastAPI

Use the FastAPI lifespan event handler to manage the Hangar lifecycle. Store the instance on `app.state` for dependency injection.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from mcp_hangar import Hangar

@asynccontextmanager
async def lifespan(app: FastAPI):
    hangar = Hangar.from_config("config.yaml")
    await hangar.start()
    app.state.hangar = hangar
    yield
    await hangar.stop()

app = FastAPI(lifespan=lifespan)

@app.post("/invoke/{mcp_server}/{tool}")
async def invoke_tool(mcp_server: str, tool: str, request: Request):
    hangar: Hangar = request.app.state.hangar
    body = await request.json()
    result = await hangar.invoke(mcp_server, tool, body.get("arguments"))
    return {"result": result}

@app.get("/health")
async def health(request: Request):
    hangar: Hangar = request.app.state.hangar
    summary = await hangar.health()
    return {
        "status": "healthy" if summary.all_ready else "degraded",
        "ready": summary.ready_count,
        "total": summary.total_count,
        "mcp_servers": summary.mcp_servers,
    }
```

The `async with` context manager pattern also works in lifespan handlers:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with Hangar.from_config("config.yaml") as hangar:
        app.state.hangar = hangar
        yield
```

## Error Handling

The Facade API raises specific exceptions for different failure modes:

| Exception | When Raised |
| ----------- | ------------- |
| `ConfigurationError` | Invalid configuration, Hangar not started, builder already built, `.set_intervals()` called |
| `ValueError` | `principal=` is `Principal.system()`, or a `.max_concurrency()` value outside 1-100 |
| `McpServerNotFoundError` | No MCP server or group has that name |
| `ToolNotFoundError` | The MCP server does not have the tool |
| `ToolCallFailedError` | A control refused the call, or the call failed, including a server that fails to start |
| `TimeoutError` | Invocation exceeded `timeout_s` |

`ToolCallFailedError` is a `ToolInvocationError`, so an `except ToolInvocationError` still catches it. Its `code` is the `error_type` that `hangar_call` reports for the same call, and its message is the text `hangar_call` reports:

- A control's refusal codes include `AuthorizationDenied`, `ToolAccessDeniedError`, `ToolWithdrawnError`, `ToolDigestMismatchError`, `ValidatorDenied`, `TenantQuotaExceeded` and `CircuitBreakerOpen`.
- A failure's code is the name of the exception it raised, for example `ToolTimeoutError` or `ClientError`.
- A server that fails to start raises `ToolCallFailedError` with `code == "McpServerStartError"`, so an `except McpServerStartError` does not catch it.

```python
from mcp_hangar.domain.exceptions import (
    McpServerNotFoundError,
    ToolCallFailedError,
    ToolNotFoundError,
)

try:
    result = await hangar.invoke("math", "divide", {"a": 10, "b": 0}, principal=caller)
except ToolCallFailedError as e:
    if e.code == "McpServerStartError":
        print(f"Server failed to start: {e}")
    else:
        print(f"Call failed ({e.code}): {e}")
except (McpServerNotFoundError, ToolNotFoundError) as e:
    print(f"Not found: {e}")
except TimeoutError:
    print("Invocation timed out")
```

For available tool names on a MCP server, see the [MCP Tools Reference](../reference/tools.md).
