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
cycle, however long the failure lasts.

*Since 2.34.4* a scan that fails in part does not remove anything either. A
Kubernetes namespace whose pod listing fails (forbidden, timeout, API error)
while the API itself answers, and a discovery file that exists but is not valid
YAML or whose content fails to load, keep what they registered. Every cycle
logs `discovery_part_failed_servers_kept` at WARNING with the part, the servers
kept and, under `unreported_past_ttl`, those not reported for longer than their
TTL. Once the part answers again, a server that is no longer there is removed
one TTL later. With `namespaces` unset, a failure to list the namespaces fails
the whole scan, and one pod whose annotations do not parse no longer hides the
rest of its namespace. Before 2.34.4 both cases counted as a real absence and
removed the server once its TTL ran out.

So revoking Hangar's permission to list pods in a namespace no longer removes
that namespace's servers: drop the namespace from `namespaces` as well. With a
ClusterRole a deleted namespace lists as empty and its servers go after their
TTL. With a Role and RoleBinding per namespace, deleting the namespace deletes
the RoleBinding too, so the listing is forbidden from then on and its servers
are kept with the warning until the namespace leaves `namespaces`. Breaking a
discovery file no longer removes its server: delete the file or set
`enabled: false` in it.

A deleted file, a disabled definition, and a file refused by the trust checks
(including one that cannot be opened) still remove their server after its TTL.
So does any server a check above refuses -- a Kubernetes local mode, a Docker
label volume outside `allowed_mount_paths`, a world-writable file: it is no
longer reported, and an authoritative source removes it after its TTL.

### A changed definition

*Since 2.34.4* a discovered server whose definition changes (an edited file,
changed labels or annotations) is replaced with the new definition on the next
cycle, after its calls in flight finish (at most 30 seconds, as a graceful
reload waits). The change passes every check a new registration does. A change
that is refused -- an endpoint the SSRF policy refuses, a local mode on a
gateway that shares its state -- leaves the running definition running and is
logged once as `discovery_change_not_applied`; fix or revert the definition. A
manual scan tries a refused change again. With `auto_register: false`, or when
the change fails validation and is quarantined, it waits for
[approval](#approving-a-discovered-server) while the running definition keeps
running, and approving it applies it.

Only a server discovery registered is ever replaced: never one declared in
`config.yaml`, created over the API, or re-pointed over the API, even when a
source reports the same name. Before 2.34.4 a changed definition was refused
with `McpServer already exists` every cycle, and on an authoritative source the
server was removed and created again from the new definition once its TTL ran
out.

### Servers an operator took over

*Since 2.34.4* discovery never deletes a server it did not register. A
discovered server re-pointed over the API (`PUT /api/mcp_servers/{id}` with a
new `endpoint`), or deleted and created again over the API under the same name,
is the operator's from then on: when its source stops reporting the name,
discovery logs `discovery_deregistration_refused_not_discovered` at INFO once,
leaves the server in place, and stops tracking the name. Delete such a server
yourself with `DELETE /api/mcp_servers/{id}` if it should go.

### After a reload

*Since 2.34.10* a configuration reload leaves a discovered server alone: it keeps
running with its source, and the next scan finds it registered. If the file now
declares the same name, the file's definition applies. See
[Hot-Reload](../reference/hot-reload.md#reload-behavior).

### After a restart

With a durable storage backend (`persistence.backend: sqlite` or
`postgresql`), *since 2.34.4* a server discovery registered stays with the
source that registered it after a restart, instead of being restored as a
static server that nothing could remove. Its row records that source and the
definition it reported. When the instance takes the management lease:

- an authoritative source that no longer reports the server removes it one TTL
  later, also when it went away while the gateway was down;
- an additive source keeps it;
- a definition that changed meanwhile is handled as a change.

A discovered row written by an earlier version records no source. If its
description is still `Discovered from <source>`, only that source can take the
server over, when it next reports it, and the server stays until then. A row
whose source cannot be told, servers declared in `config.yaml`, and servers
created over the API or CLI stay static. Re-pointing a discovered server over
the API drops its recorded origin. To keep a discovered server whatever its
source reports, set `mode: additive` on the source or declare the server in
`config.yaml`.

### When the management lease changes hands

In a multi-replica deployment only the instance holding the management lease
runs discovery. *Since 2.34.4* an instance that takes the lease, including one
that held it before, rebuilds discovery tracking from the fleet as it is then:
every discovered server counts as seen at that moment, so an authoritative
source removes one it no longer reports a full TTL after the lease was taken,
not on the first cycle. A server a peer removed meanwhile is registered again
when its source reports it, and a server re-pointed over the API or CLI
meanwhile is no longer governed by discovery. Pending and quarantined entries
are kept only where the fleet still runs what this instance ran when the entry
was made; one a peer approved, replaced or removed is dropped, and the next
cycle decides again. A standalone gateway is unchanged.

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

## Approving a discovered server

A server waits for approval in one of two places: pending, when its source has
`auto_register: false` (`hangar_discovered`, `GET /api/discovery/pending`), and
quarantine, when it failed validation (`hangar_quarantine`,
`GET /api/discovery/quarantined`). A changed definition of a running server
waits in the same places while the running definition keeps running.

*Since 2.34.4* every listing shows a `definition_digest`, the full SHA-256 of
the definition. A source re-reports its definition every cycle, so pass the
digest you reviewed and the approval applies only that definition:

```bash
curl -X POST "http://localhost:8000/api/discovery/approve/svc?definition_digest=<digest>"
```

On MCP, `hangar_approve(mcp_server="svc", definition_digest="<digest>")`. If
the definition waiting has another digest, the approval is refused with
`DiscoveredDefinitionChangedError` (409 on REST) naming the current one, and
nothing changes. An approval without a digest still applies whatever waits
under the name and logs `discovery_approval_not_bound` at WARNING. Use
`definition_digest`, not the 16-character `fingerprint`, which does not bind.
The REST body and query rules, and their 400s, are in the
[REST reference](../reference/rest-api.md#approve-mcp-server).

An approval runs the input validator on the command and the source's own
policy, as an automatic registration does, and refuses a definition that fails
them or whose source is no longer registered. It still overrides the other
reasons a definition is quarantined: a failed health or schema check, and the
rate and count limits. A refused approval answers `approved: false` with
`error: "approval refused: <reason>"`, and the definition keeps waiting where
it was, with the same `definition_digest`, so a reject can still remove it.
*Since 2.34.5* the same holds when the control plane refuses the registration,
for instance because a server of that name already exists, and when the
replacement of a running server's changed definition is refused or fails; the
running server is untouched.

A pending entry is cleared once a scan no longer reports it: the source
reports the running definition again or another one under the name, or a
healthy source stops reporting the name. A quarantined change is cleared when
its source reports the running definition again, and removing a source clears
what it left waiting.

An approval and a discovery cycle on the same server take turns: an approval
that arrives mid-cycle waits for the cycle to finish and then sees what it
left, so an approval bound to a digest the cycle has since replaced is refused.
Approvals and cycles on different servers do not wait for each other.

In a cluster that shares a management lease, a manual scan (`hangar_discover`,
`POST /api/discovery/sources/{id}/scan`) and an approval are refused with 409
on an instance that does not hold the lease: send them to the one that does. A
standalone gateway always holds it.

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
