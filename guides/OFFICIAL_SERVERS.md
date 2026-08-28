# The official MCP servers

[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
publishes seven reference servers. They are the fastest way to point Hangar at
something real, and the examples in this repository use them rather than
inventing a provider.

## The seven

Tool counts are from a real run through a gateway, not from the upstream
READMEs.

| Server | Package | Tools | Transport | Wants |
| ------ | ------- | ----- | --------- | ----- |
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

## Running the stdio six behind a bridge

Six of the seven speak only stdio, and a Kubernetes Service cannot address a
pipe. The shape that works is one `mcp-proxy` per server, in the same pod or
compose service, spawning the child with its stdio attached and serving it as
Streamable HTTP; Hangar then registers each as `mode: remote`.

Three things that cost a day to find the first time:

- **Pin `mcp-proxy` to 0.12.0 or newer.** Earlier lines are SSE-only; 0.12.0 is
  the first that mounts Streamable HTTP at `/mcp` in server mode.
- **Pin the SDK to `mcp==1.28.1` in that image.** The reference servers are
  still SDK 1.x software, their own `uv.lock` files say so, and `mcp-proxy`
  0.12.0 imports `request_ctx` from `mcp.server.lowlevel.server`, which SDK
  2.0.0 no longer exports. Unpinned, `pip` takes 2.0.0 and every one of those
  containers crash-loops on the `ImportError`.
- **`mcp-proxy` does not pass its own environment to the child.** Anything the
  server needs has to be given explicitly.

One of those explicit variables matters more than it looks. `mcp-server-fetch`
extracts content with `readabilipy`, which -- *if it can see `node` on `PATH`* --
shells out to `npm install` on the first call. In an image that also carries the
TypeScript servers, node is there, so `fetch` reaches for `registry.npmjs.org`
mid-call. Behind an egress policy that does not allow it, the packets are
dropped silently, `npm` has no timeout, and the first bound anything hits is the
gateway's 60s `tools/call` timeout -- three of which trip the circuit breaker
and leave the server looking dead. Give that child a `PATH` without node and
`fetch` answers in ~200ms, with a denied host refused in 5s.

**A denied egress is a silent drop, not an error.** Any upstream that dials
out mid-call needs a timeout of its own; the policy is doing its job and the
caller cannot tell it apart from a hang.

## Governing them

Once one is registered, it is an upstream like any other:

- [Egress policy](EGRESS_POLICY.md) -- `fetch` is the obvious one to govern; a
  denied host is a refusal with a verdict, not a timeout.
- [Front-door mode](FRONT_DOOR.md) -- projects each provider's tools under
  their own names instead of the `hangar_*` API.
- [Tool-access policy](../reference/configuration.md) -- `filesystem` and `git`
  have write tools worth denying before they are worth allowing.
