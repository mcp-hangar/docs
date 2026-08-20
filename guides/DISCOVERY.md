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
```

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
| `mcp.hangar.mode` | no | `http` |
| `mcp.hangar.port` | no | `8080` |
| `mcp.hangar.group` | no | - |

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

### Filesystem

```yaml
sources:
  - type: filesystem
    mode: additive
    path: /etc/mcp-hangar/mcp_servers.d/
    pattern: "*.yaml"
    watch: true
```

MCP Server file:

```yaml
# /etc/mcp-hangar/mcp_servers.d/custom.yaml
name: custom-tool
enabled: true
mode: subprocess
connection:
  command: python
  args: [-m, my_mcp_server]
```

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
| Your package fails to import | Logged as `discovery_source_plugin_failed` and skipped; the gateway still starts |
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
| `authoritative` | Adds and removes (for dynamic environments) |

## Security

```yaml
discovery:
  security:
    max_mcp_servers_per_source: 100
    max_registration_rate: 10  # per minute
    require_health_check: true
    quarantine_on_failure: true
```

These apply to every source. Rules that only one kind of infrastructure
understands — Kubernetes namespaces, and whatever a third-party source cares
about — belong to that source; see
[Kubernetes](#kubernetes) and [Refusing what it discovers](#refusing-what-it-discovers).

A discovered server is registered through the same command as one created over
the REST API, so it passes the same duplicate and SSRF checks, and the
`McpServerRegistered` event carries `source: discovery:<type>`.

> **The SSRF check applies to discovered endpoints too**, and a container or pod
> address is private by definition. A source that reports an HTTP endpoint on a
> private address is refused registration — see
> [#771](https://github.com/mcp-hangar/mcp-hangar/issues/771).
>
> **`McpServerRegistered` is not written to the event store.** It is published to
> in-process subscribers only, so a server's registration does not appear in its
> stream — updates, lifecycle transitions and tool invocations do. Do not rely on
> the event history to answer "when was this server added, and by which source"
> — see [#772](https://github.com/mcp-hangar/mcp-hangar/issues/772).

## Tools

| Tool | Description |
| ------ | ------------- |
| `hangar_discover` | Trigger discovery cycle |
| `hangar_sources` | List sources with status |
| `hangar_quarantine` | List quarantined MCP servers |
| `hangar_approve` | Approve quarantined MCP server |

## Conflict Resolution

1. **Static config wins** — Manual config always takes precedence
2. **Higher priority source wins** — K8s (1) > Docker (2) > Filesystem (3) > Entrypoints (4) > any other source (99)
3. **TTL expiration** — Authoritative sources deregister after TTL

## Prometheus Metrics

| Metric | Description |
| -------- | ------------- |
| `mcp_hangar_discovery_mcp_servers` | MCP servers per source (Gauge) |
| `mcp_hangar_discovery_registrations_total` | New registrations |
| `mcp_hangar_discovery_quarantine_total` | Refused registrations, by `reason` — including a source's own policy |
| `mcp_hangar_discovery_errors_total` | Errors by source |
| `mcp_hangar_discovery_cycle_duration_seconds` | Cycle duration (Histogram) |
