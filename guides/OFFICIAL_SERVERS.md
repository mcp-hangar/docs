# The official MCP servers

[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
publishes seven reference servers. They are the fastest way to point Hangar at
something real, and the examples in this repository use them rather than
inventing a provider.

## The seven

Tool counts are from a real run through a gateway, not from the upstream
READMEs.

| Server | Package | Tools | Transport | Wants |
|---|---|---|---|---|
| `everything` | `@modelcontextprotocol/server-everything` | many | **stdio and HTTP** | nothing |
| `fetch` | `mcp-server-fetch` (PyPI) | 1 | stdio | network egress |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | 14 | stdio | a sandbox directory |
| `git` | `mcp-server-git` (PyPI) | 12 | stdio | a repository path |
| `memory` | `@modelcontextprotocol/server-memory` | 9 | stdio | a writable file for the graph |
| `sequentialthinking` | `@modelcontextprotocol/server-sequential-thinking` | 1 | stdio | nothing (stateful across calls) |
| `time` | `mcp-server-time` (PyPI) | 2 | stdio | nothing |

There is **no official SQLite server**: the upstream one is archived.

## Two things that decide how you wire them

**Only `everything` speaks HTTP.** Its transport is an argument --
`streamableHttp`, `sse`, or `stdio` (the default). Every other server is
stdio-only, which matters as soon as Hangar is not on the same machine: a
gateway in a container cannot attach to another container's stdin. Give a
stdio server an HTTP bridge (`mcp-proxy` beside it in the same pod or compose
service) or run it as a subprocess of the gateway.

**Prefer the packages to the published images.** Docker publishes `mcp/*`
images for these, and they are official -- but `mcp/everything`,
`mcp/filesystem` and `mcp/memory` were last rebuilt in 2025, while the packages
release continuously. That is not only a CVE-freshness argument: the 2025 build
of `mcp/everything` **ignores the transport argument** and comes up on stdio, so
a gateway pointed at its HTTP port gets `Connection refused`. `mcp/fetch` is
current.

## The three shapes

### Subprocess -- Hangar starts it

The simplest, and the right default when Hangar runs on a host with `npx` or
`uvx` available.

```yaml
mcp_servers:
  filesystem:
    mode: subprocess
    command: [npx, -y, "@modelcontextprotocol/server-filesystem"]
    args: ["/absolute/path/to/sandbox"]
    idle_ttl_s: 300

  time:
    mode: subprocess
    command: [uvx, mcp-server-time]
    idle_ttl_s: 300
```

Not available inside the published Hangar image: it is `python:3.14-slim` plus
the wheel, with no node and no `uv`.

### Remote -- something else runs it

```yaml
mcp_servers:
  everything:
    mode: remote
    endpoint: http://everything:3001/mcp
```

The provider runs beside the gateway -- another compose service, another pod --
and speaks HTTP. Today that means `everything`, or any stdio server behind a
proxy. `examples/quickstart/` in the core repository is exactly this shape.

### Container -- Hangar starts the container

```yaml
mcp_servers:
  everything:
    mode: container
    image: docker.io/mcp/everything:latest
```

**Container mode shells out to a `podman` or `docker` CLI on the host running
Hangar.** It is not the Docker API, so mounting `/var/run/docker.sock` into a
containerised gateway does not enable it -- the published image has neither CLI
and says so:

```
No container runtime (podman or docker) found on PATH.
```

Use this when Hangar runs on the host, not in a container. See
[Container MCP servers](CONTAINERS.md).

## Governing them

Once one is registered, it is an upstream like any other:

- [Egress policy](EGRESS_POLICY.md) -- `fetch` is the obvious one to govern; a
  denied host is a refusal with a verdict, not a timeout.
- [Front-door mode](FRONT_DOOR.md) -- projects each provider's tools under
  their own names instead of the `hangar_*` API.
- [Tool-access policy](../reference/configuration.md) -- `filesystem` and `git`
  have write tools worth denying before they are worth allowing.
