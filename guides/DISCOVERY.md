# MCP Server Discovery

Auto-discover MCP servers from Docker, Kubernetes, filesystem, or Python entrypoints.

## Configuration

```yaml
discovery:
  enabled: true
  refresh_interval_s: 30
  auto_register: true

  sources:
    - type: docker
      mode: additive
```

## Sources

### Docker/Podman

```yaml
sources:
  - type: docker
    mode: additive
    socket_path: /var/run/docker.sock  # optional
    allowed_mount_paths: ["/srv/mcp-data"]  # optional; see the volumes label
```

The source lists every container with `mcp.hangar.enabled=true`, stopped and
created-but-never-started ones included.

Container labels:

```yaml
# docker-compose.yml
services:
  my-mcp-server:
    image: my-mcp-server:latest
    labels:
      mcp.hangar.enabled: "true"
      mcp.hangar.name: "my-mcp-server"
      mcp.hangar.mode: "http"
      mcp.hangar.port: "8080"
```

| Label | Required | Default |
| ------- | ---------- | --------- |
| `mcp.hangar.enabled` | yes | - |
| `mcp.hangar.name` | no | container name |
| `mcp.hangar.mode` | no | `container` (Hangar runs the image); `http` or `sse` connects to the running container |
| `mcp.hangar.port` | no | `8080` (`http`/`sse` mode) |
| `mcp.hangar.path` | no | `/mcp` (`http`/`sse` mode): the MCP endpoint's path |
| `mcp.hangar.ttl` | no | `90`: seconds an `authoritative` source keeps the server after it stops being reported |
| `mcp.hangar.read-only` | no | `true` (`container` mode): run the container with a read-only root filesystem. `"false"` opts out |
| `mcp.hangar.volumes` | no | - (`container` mode): comma-separated `host:container[:mode]` mounts, honoured only under `allowed_mount_paths` |
| `mcp.hangar.command` | no | - (`container` mode): accepted, but not passed to the container today; the image's own command runs |

*Since 2.34.2* a container Hangar runs from a label gets a read-only root
filesystem by default, as a declared container does, and a `mcp.hangar.volumes`
label is honoured only when every host path in it is absolute and under one of
the source's `allowed_mount_paths`. `/` and any `*.sock` file are refused even
there, and `~` is not expanded. A container whose label names anything else is
not registered at all, rather than registered without its mounts, and is logged
once as `docker_discovery_label_volumes_refused`. With no `allowed_mount_paths`,
any container carrying the label is refused. There is no `group` label: a
discovered server joins no group.

### Kubernetes

Needs the Kubernetes Python client, which is an extra — `pip install
mcp-hangar[kubernetes]`. The published image ships it. Without it Hangar starts
and logs `discovery_source_unavailable`, and this source discovers nothing.

```yaml
sources:
  - type: kubernetes
    mode: authoritative
    namespaces: [mcp-servers]
    label_selector: "app.kubernetes.io/component=mcp-server"
    in_cluster: true
    allowed_namespaces: [mcp-servers]          # optional allowlist
    denied_namespaces: [kube-system, default]  # default
    allow_local_modes: false                   # default; see below
```

A pod in a denied namespace is refused registration even when it carries the
annotations. `denied_namespaces` wins over `allowed_namespaces`; with no
allowlist, everything not denied is accepted.

> **These two keys moved.** They used to live under `discovery.security`, where
> the core applied them behind a check on the source's name. The old location
> still works and logs `discovery_namespace_policy_deprecated_location` on every
> startup that uses it; the new one wins when both are set.

Pod annotations:

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    mcp-hangar.io/enabled: "true"
    mcp-hangar.io/name: "data-processor"
    mcp-hangar.io/mode: "http"
    mcp-hangar.io/port: "8080"
```

| Annotation | Default |
| ------------ | --------- |
| `mcp-hangar.io/enabled` | required, `"true"` |
| `mcp-hangar.io/name` | pod name |
| `mcp-hangar.io/mode` | `http`; also `sse` or `remote`. Any other mode needs `allow_local_modes` |
| `mcp-hangar.io/port` | `8080` |
| `mcp-hangar.io/path` | `/mcp`: the MCP endpoint's path |
| `mcp-hangar.io/health-path` | `/health` |
| `mcp-hangar.io/ttl` | `90` seconds |
| `mcp-hangar.io/command` | - (local modes only) |

*Since 2.34.2* the source registers only pods Hangar connects to. A pod whose
`mcp-hangar.io/mode` asks for anything else, such as `subprocess` with
`mcp-hangar.io/command`, which would run that command on Hangar's own host, is
skipped and logged once as `kubernetes_discovery_local_mode_refused`. If
whoever can create pods in the watched namespaces is trusted to choose what
Hangar runs on its host, set `allow_local_modes: true` on the source. The value
must be the boolean `true`; a string such as `"yes"` leaves the source closed.
There is no `group` annotation: a discovered server joins no group.

### Filesystem

```yaml
sources:
  - type: filesystem
    mode: additive
    path: /etc/mcp-hangar/mcp_servers.d/
    pattern: "*.yaml"
```

The source reads the directory every `refresh_interval_s`. A `watch: true` key
is accepted, but file watching needs the `watchdog` package, which Hangar does
not install, and nothing acts on its events, so polling is what runs either
way; the log says `Filesystem discovery source started (watching disabled)`.

MCP Server file:

```yaml
# /etc/mcp-hangar/mcp_servers.d/custom.yaml
name: custom-tool
enabled: true
mode: subprocess
ttl: 90          # optional; seconds an authoritative source keeps it once the file is gone
connection:
  command: python
  args: [-m, my_mcp_server]
```

A definition file names a command Hangar runs, so *since 2.34.2* the source
skips a file, and logs `filesystem_discovery_file_refused` once with the reason,
when:

- it resolves, through a symlink, to a path outside the source's `path`;
- it is not a regular file;
- on POSIX, it is world-writable;
- on POSIX, the source's `path`, or a directory between it and the file, is
  world-writable. A sticky directory such as `/tmp` counts.

Group-writable files and directories, files owned by another user, and a file
on a filesystem mounted read-only are not refused, so a Kubernetes ConfigMap or
Secret volume works unchanged. An `emptyDir` is writable and its root is 0777,
so it is refused: fill it from an init container into a subdirectory that is
not world-writable, or mount a ConfigMap. There is no setting to turn the checks
off.

### Python Entrypoints

```yaml
sources:
  - type: entrypoint
    mode: additive
    group: mcp.mcp_servers
```

```toml
# pyproject.toml
[project.entry-points."mcp.mcp_servers"]
my_mcp_server = "my_package.server:create_server"
```

```python
def create_server():
    return {
        "name": "my-tools",
        "mode": "subprocess",
        "command": ["python", "-m", "my_package.server"]
    }
```

## Adding a source of your own

Consul, Nomad, an internal registry — a source Hangar does not ship is a package
of yours. Core is not modified and never learns your option names.

Implement the port — three members:

```python
# my_package/consul_source.py
from mcp_hangar.domain.discovery.discovered_mcp_server import DiscoveredMcpServer
from mcp_hangar.domain.discovery.discovery_source import DiscoveryMode, DiscoverySource


class ConsulSource(DiscoverySource):
    def __init__(self, mode: DiscoveryMode, *, datacenter: str, token: str | None = None) -> None:
        super().__init__(mode=mode)
        self._datacenter = datacenter
        self._token = token

    @property
    def source_type(self) -> str:
        return "consul"

    async def discover(self) -> list[DiscoveredMcpServer]:
        ...  # return what is there now; the orchestrator diffs it for you

    async def health_check(self) -> bool:
        ...  # can this source be reached at all
```

Advertise a factory under the `mcp_hangar.discovery_sources` entry point group:

```python
def create_source(mode: DiscoveryMode, config: dict) -> ConsulSource:
    return ConsulSource(mode, datacenter=config["datacenter"], token=config.get("token"))
```

```toml
# pyproject.toml
[project.entry-points."mcp_hangar.discovery_sources"]
consul = "my_package.consul_source:create_source"
```

Install the package next to Hangar and configure it like any built-in:

```yaml
sources:
  - type: consul
    mode: additive
    datacenter: dc1
    token: ${CONSUL_TOKEN}
```

Hangar reads `type` and `mode`. Everything else in that entry is handed to your
factory untouched, so `datacenter` and `token` are yours to name and yours to
validate.

| Situation | What happens |
| ----------- | -------------- |
| `type` has no factory | Startup **fails** — a configured source that silently watches nothing is worse than a crash |
| Your package fails to import | Logged as `discovery_source_plugin_failed` and skipped; the gateway still starts unless a configured source needs that `type`, which then fails startup as above |
| Your entry point names a built-in | Logged as `discovery_source_plugin_ignored`; a plugin cannot quietly shadow `kubernetes` |

### Refusing what it discovers

A source can veto its own findings in its own vocabulary. This runs before
Hangar's checks (rate, count, health, schema), and Hangar never interprets it —
the reason and details reach the operator and the quarantine report as written:

```python
from mcp_hangar.domain.discovery.discovery_source import SourcePolicyViolation


def policy_violation(self, mcp_server: DiscoveredMcpServer) -> SourcePolicyViolation | None:
    datacenter = mcp_server.metadata.get("datacenter", "")
    if datacenter not in self._allowed:
        return SourcePolicyViolation(
            reason=f"Datacenter {datacenter!r} is not allowed",
            details={"datacenter": datacenter, "allowed": sorted(self._allowed)},
        )
    return None
```

The hook is optional. A source with no rules of its own overrides nothing —
which is also why the Kubernetes namespace policy is the same mechanism rather
than a special case in core.

## Discovery Modes

| Mode | Behavior |
| ------ | ---------- |
| `additive` | Only adds MCP servers, never removes |
| `authoritative` | Adds, and removes a server the source stopped reporting once its TTL has passed |

*Since 2.34.2* an `authoritative` source deregisters a server it no longer
reports once the server's TTL has passed since it was last seen: 90 s by
default, or `mcp.hangar.ttl` on a container, `mcp-hangar.io/ttl` on a pod,
`ttl` in a file. Before 2.34.2 nothing was removed until a restart, whatever
the mode. A server that comes back within its TTL is left running. Servers from
`config.yaml` are never touched.

"No longer reported" means a cycle in which the source answered and reports
itself healthy afterwards. A source whose scan fails -- Docker when the daemon
does not answer, a filesystem `path` that is missing -- removes nothing that
cycle, however long the failure lasts. Two cases still count as a real absence
and remove the server once its TTL has run out: a Kubernetes namespace whose pod
listing fails while the API itself answers, and a discovery file that stops
parsing. A server a check above now refuses -- a Kubernetes local mode, a Docker
label volume outside `allowed_mount_paths`, a world-writable file -- is no
longer reported either, so an authoritative source removes it after its TTL.

A discovered definition that changes is not applied: the source reports it
again, its registration is refused with `McpServer already exists` every cycle,
and the server keeps its old definition until it is removed or Hangar restarts.

## Security

```yaml
discovery:
  security:
    max_mcp_servers_per_source: 100
    max_registration_rate: 10  # per minute
    require_health_check: true
    quarantine_on_failure: true
```

`require_health_check` asks an HTTP server's health path before registering
it: `mcp-hangar.io/health-path` on a Kubernetes pod, `/health` by default.
Since 2.27.1 a 404 there is not a failure by itself: the check then sends an
MCP `initialize` to the server's MCP path (`mcp-hangar.io/path`, default
`/mcp`) and passes on a JSON-RPC result. A server that serves only MCP no longer
needs `require_health_check: false`. A 5xx or a timeout on the health path
still fails the check, with no fallback.

These apply to every source. Rules that only one kind of infrastructure
understands — Kubernetes namespaces, and whatever a third-party source cares
about — belong to that source; see
[Kubernetes](#kubernetes) and [Refusing what it discovers](#refusing-what-it-discovers).

A discovered server is registered through the same command as one created over
the REST API, so it passes the same duplicate and SSRF checks, and the
`McpServerRegistered` event carries `source: discovery:<type>`.

> **The SSRF check applies to discovered endpoints too**, scoped to what the
> container runtime reported. A container or pod address is private by
> definition, so the `docker` and `kubernetes` sources pass along the addresses
> the runtime reported for that container or pod, and a discovered endpoint may
> resolve to those addresses and nowhere else. A source that reports none --
> `filesystem`, `entrypoint`, or a third-party source that sets no
> `runtime_addresses` -- gets the same policy as a hand-registered server, so
> an endpoint on a private address is refused. Link-local and cloud metadata
> addresses are refused whatever the source. See
> [#771](https://github.com/mcp-hangar/mcp-hangar/issues/771).
>
> **`McpServerRegistered` is written to the server's stream** in the event
> store, with its `source`, so the event history answers "when was this server
> added, and by which source" -- see
> [#772](https://github.com/mcp-hangar/mcp-hangar/issues/772).

## Tools

| Tool | Description |
| ------ | ------------- |
| `hangar_discover` | Trigger discovery cycle |
| `hangar_sources` | List sources with status |
| `hangar_discovered` | List pending MCP servers (with `auto_register: false`) |
| `hangar_quarantine` | List quarantined MCP servers |
| `hangar_approve` | Approve a pending or quarantined MCP server |

## Conflict Resolution

1. **Static config wins** — Manual config always takes precedence
2. **Higher priority source wins** — K8s (1) > Docker (2) > Filesystem (3) > Entrypoints (4) > any other source (99)
3. **TTL expiration** — Authoritative sources deregister a server they stopped reporting after its TTL (see [Discovery Modes](#discovery-modes))

## Prometheus Metrics

| Metric | Description |
| -------- | ------------- |
| `mcp_hangar_discovery_mcp_servers` | MCP servers per source (Gauge) |
| `mcp_hangar_discovery_registrations_total` | New registrations |
| `mcp_hangar_discovery_quarantine_total` | Refused registrations, by `reason` — including a source's own policy |
| `mcp_hangar_discovery_errors_total` | Errors by source |
| `mcp_hangar_discovery_cycle_duration_seconds` | Cycle duration (Histogram) |
