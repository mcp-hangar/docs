---
title: Upgrade Guide
---

This guide covers user-visible migration steps between MCP Hangar releases.

## Upgrade to 2.12.0

### `truncation.cache_driver: redis` now fails closed (#1007)

If Redis cannot actually serve the continuation cache -- the `redis` package
is missing, the URL does not parse, or the server cannot `SETEX` (a Sentinel
listen port) -- the gateway now **refuses to start** instead of silently
falling back to the per-replica memory cache. If your deployment booted with
`cache_driver: redis` before this release, Redis was never actually in use;
either fix the connection (the image now ships the `redis` extra, #1008) or
set `cache_driver: memory` explicitly. A truncated response no longer carries
a `continuation_id` unless the full payload was actually stored.

`pip install mcp-hangar[redis]` provides the client; it is deliberately not
part of the base install or the `full` extra.

## Upgrade to 2.11.0

### the unused-surface sweep (#969)

Nine verified-dead surfaces left over from the factory cut are gone. None had
a caller in `src/`; if you imported them in your own code, the replacements
are listed:

- **`HangarError` / `Rich*` errors, factories, `ErrorClassifier`**
  (`mcp_hangar.errors`, also re-exported from the package root). The live
  hierarchy is `mcp_hangar.domain.exceptions`; `is_retryable` stays and keeps
  matching timeout/connection-style exceptions by pattern.
- **`ProgressTracker` / `create_progress_tracker`** (`mcp_hangar.progress`,
  module deleted). MCP progress notifications are a different, live feature.
- **`HealthEndpoint` / `HealthCheck` / `get_health_endpoint`**
  (`mcp_hangar.observability`). The live probes are the `/health/*` routes;
  event-store durability get/set remains in `observability.health`.
- **`mcp_hangar.domain.bundles`** (starter/developer/data bundle catalog).
  Hot-loading from the registry (`hangar_load`) is the live path.
- **`AuditService`** (`domain.services`). Live audit is `AuditEventHandler`
  over `IAuditRepository`.
- **Tenant/catalog/package exception cluster** (`TenantNotFoundError`,
  `QuotaExceededError`, `CatalogItemNotFoundError`,
  `PackageVerificationError`, ...) plus `McpServerEntry` and
  `CatalogItemId`. There is no catalog API these could describe.
- **`HangarLoadResult` / `HangarUnloadResult`** and REST
  `serialize_tool_info` / `serialize_health_info`; the tools return dicts and
  REST serializes via `.to_dict()`.
- **Metrics helpers** `init_metrics`, `timed`, `record_*` for
  detection/behavioral features that never shipped producers.
- **`initialize_runtime` / `shutdown_runtime`** (`bootstrap.runtime`) and the
  `trace_tool_invocation` decorator; `create_runtime`, `init_tracing` and
  `get_tracer` stay.

## Upgrade to 2.10.0

### `config.yaml` warns about a key nothing reads

Unknown keys were kept and ignored at every level. They are now reported, with
the offending key and the allowed set named:

```text
auth has unknown key(s) ['enabledd']; allowed keys: ['allow_anonymous',
'api_key', 'enabled', 'oidc', 'opa', 'rate_limit', 'role_assignments', 'storage']
```

**This release warns and starts anyway.** Refusing is correct -- a misspelled
`auth` key is a gateway that believes it enabled authentication -- and is also a
breaking change for anyone carrying a stale key, so it gets a release of notice
instead of arriving in a patch.

- `HANGAR_CONFIG_STRICT=1` refuses now, which is what to set in CI.
- **the default becomes refusal in 3.0.0.** Any `unknown_config_key` warning in
  your logs today is a config that will not load then.

Checked: top-level section names, the direct keys of each section, and the keys
of an `mcp_servers.<id>` spec. Not checked: anything deeper. That is where a
single reader exists to enumerate from -- below it the keys live in around
twenty modules, and a schema hand-copied from twenty readers drifts into
rejecting valid configuration, which is worse than accepting a typo.

**New: `mcp-hangar config check [path]`.** Answers the same question without
starting a gateway, and is always strict. Exit 0 clean, 1 unknown key, 2 the
file is missing or is not YAML. It defaults to `$MCP_CONFIG`, then `config.yaml`.

```console
$ mcp-hangar config check config.yaml
FAIL config.yaml: 1 key(s) nothing reads:

  mcp_servers.math has unknown key(s) ['commandd']; allowed keys: [...]
```

## Upgrade to 2.9.0

Drop-in for every deployment that runs the gateway. Nothing about a served
Hangar changes. One tool starts working, and a Python API that no shipped code
path ever executed is gone.

### `hangar_load` can now succeed, and wants `uvx` or `npx` on PATH

Hot-loading has been enabled by default and unable to complete since it shipped:
bootstrap handed its resolver a runtime table with every entry `False` and an
empty installer list, so every call answered

```json
{"status": "failed", "message": "No compatible package found (missing runtime?)",
 "warnings": ["Available runtimes: []"]}
```

It now resolves `pypi` packages through `uvx` and `npm` packages through `npx`,
and reports availability from the installers rather than from a hardcoded table.

The runtime has to be on the gateway process's PATH, which is the part to check
before expecting different behaviour:

- **the published container image carries neither `uvx` nor `npx`**, so
  hot-loading still fails there — now with a message naming what is missing
  rather than an empty list. Derive your own image from ours and add `uv`,
  Node, or both if you want it working in a container.
- running from a `pip install`, install [uv](https://docs.astral.sh/uv/) for
  PyPI-published servers and Node for npm-published ones. Either alone is fine.

`oci` and `mcpb` packages remain unloadable, deliberately: OCI needs a container
runtime the image does not ship, and `mcpb` has no defined install path. Both
are now reported *unavailable* instead of being selected and then dropped.

Nothing to do if you do not use `hangar_load`. `hot_loading.enabled: false`
keeps the tool switched off.

### The `fastmcp_server` factory stack is gone

Removed from `mcp_hangar.fastmcp_server`: `MCPServerFactory` with its
`builder()` and `create_asgi_app()`, `MCPServerFactoryBuilder`,
`HangarFunctions`, `ServerConfig`, the thirteen `Hangar*Fn` protocols, and the
ASGI combiners `create_health_routes`, `create_combined_asgi_app` and
`create_auth_combined_app`.

**Nothing about a running Hangar changes.** No shipped code constructed any of
it. `serve --http` builds its MCP server in `mcp_hangar.server.bootstrap` and
its ASGI app in `mcp_hangar.server.lifecycle.mcp_app_for_serving`, and has never
gone through the factory. The two assemblies had drifted far enough to prove it:
the factory mounted flat `/health` and `/ready`, while a running Hangar serves
`/health/live`, `/health/ready`, `/health/startup` and `/metrics`.

Keeping a second construction path that looked serviceable is what made four
bugs possible (#592, #594, #595, #596): each was a capability wired into the
factory, which made it appear wired and shipped it dead.

**If you were embedding through the factory** there is no drop-in replacement,
because the factory was never how the product ran. Either run the gateway
(`mcp-hangar serve --http`) and drive it over MCP or the REST API, or call the
composition root the CLI itself uses: `server.bootstrap` to build and register,
`lifecycle.mcp_app_for_serving` for the ASGI app, and
`server.api.middleware.create_auth_enforced_app` to apply the same
authentication. Those are tested on every PR and are what a released Hangar
executes.

`HANGAR_SERVER_NAME` is unchanged and still exported from
`mcp_hangar.fastmcp_server`. The v0.4.0 note further down names the factory as
the successor to `setup_fastmcp_server()`; it describes what that release did
and stays as history.

## Upgrade to 2.8.0

Two things can break a build rather than a deployment: an extra that no longer
exists, and a bundled monitoring stack that has moved to the Helm chart.

### `pip install mcp-hangar[containers]` now fails

The `containers` extra is gone. It installed `testcontainers` for a test tier
that never ran — those tests were gated behind `--run-containers` / `--run-slow`
and no CI job, `Makefile` target or script ever passed either flag, so every one
of them reported `skipped` on every run. Nothing in the shipped package imported
it.

Drop `[containers]` from your install line. If you depended on `testcontainers`
yourself, depend on it directly.

### The bundled compose monitoring stack is gone

`monitoring/` and `docker-compose.monitoring.yml` are removed from the
repository. The four Grafana dashboards and the 30 Prometheus alert rules ship
with the Helm chart instead: `dashboards.enabled` renders them as
sidecar-labelled ConfigMaps, `prometheusRule.enabled` renders a `PrometheusRule`.

Instrumentation is untouched — `/metrics`, tracing and the OTLP exporter are
unchanged; only bundled config moved. There is no one-command local Grafana any
more. If you were running it, either use the chart or keep a copy of the compose
file from the 2.7.0 tag.

### The published container runs Python 3.14

`pip install` still supports 3.11 through 3.14, and 3.14 is now a required CI
citizen rather than an advisory one. Relevant only if you build on top of our
image and pin something against the interpreter version.

### Three unused symbols left the application layer

`CallbackAlertSink` and `LogAuditStore` are gone from
`mcp_hangar.application.event_handlers`, and `detect_runtime_availability` with
its `IRuntimeChecker` protocol from `mcp_hangar.application.services`. None had a
caller outside this repository's own tests.

- **`CallbackAlertSink`** — production `get_alert_handler()` builds a
  `LogAlertSink`. To capture alerts in your own code, implement the ABC:

  ```python
  from mcp_hangar.application.event_handlers.alert_handler import Alert, AlertSink

  class CapturingSink(AlertSink):
      def __init__(self) -> None:
          self.alerts: list[Alert] = []

      def send(self, alert: Alert) -> None:
          self.alerts.append(alert)
  ```

- **`LogAuditStore`** — it could not have served as an audit store: `query()`
  raised `NotImplementedError`, because a log sink cannot answer a query. Write
  the sink you want against the `AuditStore` ABC, or use the OTLP exporter path
  (`OTLPAuditEventHandler` / `IAuditExporter`), which is built for shipping
  audit records off the box.

- **`detect_runtime_availability`** — no replacement, deliberately. Ask the
  installer you care about (`is_runtime_available()`) and construct the
  `RuntimeAvailability` yourself, which is all the removed function did, in a
  fixed order, for a list it did not validate.

`AlertSink`, `Alert`, `LogAlertSink`, `AlertEventHandler`, `get_alert_handler`,
`AuditRecord`, `AuditStore`, `InMemoryAuditStore`, `AuditEventHandler`,
`get_audit_handler`, `PackageResolver` and `RuntimeAvailability` are unchanged.

## Upgrade to 2.7.0

Drop-in for most deployments. Two behaviours change without a config change:
`approval_channel`, which was recorded and ignored, now selects where approvals
are notified; and the MCP endpoint stops handing out session ids. Read the
`approval_channel` section if any of your policies set it, and the session
section if anything in front of your pods pins traffic.

### The MCP endpoint no longer hands out a session id

`initialize` returns no `Mcp-Session-Id`, and no request needs one.

A session lived in one replica's memory, so a client that initialized against one
pod and called against another was told `Session not found` -- 13 of 15 attempts
through a three-replica Service. Session affinity papered over that and could not
fix it: a pin does not outlive its pod, so a rolling restart or a scale-down took
the session with it.

| | before | from 2.7.0 |
|---|---|---|
| `initialize` | returns `Mcp-Session-Id` | returns no session id |
| a request carrying a stale or foreign `Mcp-Session-Id` | `Session not found` | served; the header is ignored |
| `DELETE /mcp` | `200` | **`405 Method Not Allowed`** |

The last row is the only one that can surface in a client's logs. There is no
session to terminate, so teardown is refused rather than acknowledged.

**What this does not change.** Nothing about the 2026-07-28 revision, which has
no sessions at all and was already served this way. Nothing about session
*suspension* (`/api/sessions`), which keys on the caller identity from
`x-session-id` or the JWT `sid` claim and never on the transport. Nothing about
authorization, which is per request.

**Deployments.** Sticky routing is no longer a requirement for a replica set --
see [running more than one replica](cookbook/25-multiple-replicas.md). Existing
pinning is now merely unhelpful rather than wrong, so there is no rush to remove
it; leave it if you still run an older gateway behind the same ingress.

### `front_door` no longer serves an empty tool list after a restart

Also fixed here, and worth knowing whether it happened to you. In
`tool_access.mode: front_door`, `tools/list` **is** the per-tenant projection, and
the projection was built from whatever that replica had started. A replica that
had started nothing served an empty list to a valid tenant, with no client-
reachable way to fix it, and two replicas that had warmed different servers
answered the same tenant differently.

A `front_door` gateway now starts every configured mcp_server at boot, on its own
thread so readiness never waits on a backend handshake. A backend that fails to
start is logged as `front_door_warmup_failed` rather than costing the others their
projection. `egress` is unchanged: backends still start lazily on first use.

### A consent gate no longer disappears on restart

Fixed, not a migration step — but worth knowing whether it happened to you.

The tool-access-policy store held `allow_list` and `deny_list` and nothing else,
and the startup replay rebuilt policies from those two fields, assigning over
whatever the YAML had already registered. A server with `tools.approval_list` in
its config and **any** prior policy update over the REST API came back **ungated**
after a restart: the tools it named ran without being held, and the startup check
that guards this class saw no `approval_list` left to demand a gate, so the boot
was clean.

The store now persists the approval fields and the replay hands back whole
policies. An existing database is widened in place on first open. A row written
by an older build carries no approval columns; rather than let that erase a gate
one last time, the replay carries the in-force gate forward and logs
`tap_replay_carried_approval_gate`.

Nothing to do. If a gate was lost to this, it is back on the next restart — the
YAML declaration was never what went missing. If you keep audit records, calls to
`approval_list` tools between an affected restart and this upgrade ran without a
human decision.

### `approval_channel` now routes, and the built-in channel is renamed

`approval_channel` was documented as a policy's delivery channel and merged
carefully across scope narrowing — and dispatched nowhere. One delivery, built
from the global `approvals.channel`, handled every approval whichever policy
raised it. A config that set `approval_channel: slack` on one server and
something else on another got one channel, silently.

They now route as written. **Check your policies before upgrading**: if two
servers name different channels and only one adapter is installed, the other
now degrades to `noop` where it previously borrowed the global channel.

The core channel formerly called `dashboard` is now `event_stream`. It was named
after a management UI that shipped with the Hangar Cloud tier and was archived
with it, and it never pushed to that UI anyway — its `send` wrote a log line
while its docstring claimed a WebSocket integration that was never wired. The
new name points at the surface that does carry the notification: the
`ToolApprovalRequested` domain event on `/api/ws/events`.

`channel: dashboard` still resolves, to the same delivery, and logs
`approval_delivery_channel_renamed` once at boot. No config change is required.

### An armed gate now says when nobody is listening

A policy that gates a tool while its channel reaches nothing outside the process
— `noop`, or a vendor name no installed package claims — is now reported at
startup:

```text
subsystem_configured_but_unreachable
  subsystem=approval_delivery
  required_by="tools.approval_list on mcp_server:payments (channel 'slack')"
  fail_closed=False
```

The gateway still starts. The gate is fail-closed by timeout, so what is missing
is a signal rather than enforcement, and refusing the boot over a notification
channel would trade a degraded notify path for an outage. A deployment that
wants the refusal opts in:

```yaml
approvals:
  delivery:
    required: true
```

Three metrics land with it —
`mcp_hangar_approval_requests`, `mcp_hangar_approval_deliveries` and
`mcp_hangar_approval_decisions`, all labelled by channel. See
[Observability → Approval Gate](guides/OBSERVABILITY.md).

### Removed

`hangar_approve_prompt`, an MCP tool nothing registered, whose docstring pointed
at an `approvals.channel: mcp_prompt` that no builtin or entry point has provided
since 2.0. If you were calling it, you were getting a `tool not found`.

## Upgrade to 2.6.0

Not drop-in. Two changes can stop a gateway that works today, and both are the
same shape: enforcement that was advertised and did not run now runs. Read the
first two sections before you upgrade.

A gateway with authentication off is unaffected by everything here except the
boot refusal in the first section.

### Per-tenant digest pins now refuse to boot without authentication

A digest pin could only be addressed to a tenant, and the tenant reaches the
enforcement path from the authenticated principal and from nowhere else. So on a
gateway with `auth.enabled: false`, where every caller is anonymous and carries
no tenant, **no pin was ever matched**: drift stayed computable and nothing
stopped it, while `initialize` advertised `io.mcp-hangar.digest-pinning` with all
three enforcement modes. The same miss reached the task path, where nothing bound
a relayed task to a digest, so the fail-closed re-verification on result
retrieval had nothing to check.

Such a configuration now fails the boot, naming the pins it found and the auth
setting that makes them unmatchable, rather than serving a guarantee it cannot
keep.

Two ways forward. Turn authentication on, so callers arrive carrying the tenant
the pins name — or move the pins to the all-tenants block added in this release,
which holds every caller including an anonymous one:

```yaml
mcp_servers:
  payments:
    tool_projection:
      digest_enforcement: block
      pins:                       # every caller, including an anonymous one
        refund: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
      tenant_overrides:
        "tenant:a":
          pins:                   # this tenant only; wins over the block above
            refund: fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210
```

Both forms can be used together; resolution is narrowest first. A gateway with
authentication on is unaffected — its per-tenant pins were being enforced and
continue to be.

### The `hangar_*` tools now require permissions

`hangar_call` authorized every call it dispatched. The other twenty-one
`hangar_*` tools authorized nothing, so with authentication on any valid
credential could stop a server, load one, reload the configuration or approve a
discovered upstream over MCP — while the same operations over the REST API were
refused for the same identity in the same process.

Authorization is now resolved from the tool name, mirroring the REST route that
performs the same operation. No permission was invented and no built-in role
changed.

| Tool | Permission | Built-in roles that hold it |
| --- | --- | --- |
| `hangar_list`, `hangar_status`, `hangar_details`, `hangar_tools`, `hangar_health` | `mcp_servers:read` | admin, provider-admin, developer, viewer |
| `hangar_start`, `hangar_stop`, `hangar_warm` | `mcp_servers:lifecycle` | admin, developer |
| `hangar_load`, `hangar_unload` | `mcp_servers:write` | admin, developer |
| `hangar_reload_config` | `config:reload` | admin |
| `hangar_discovered`, `hangar_sources` | `discovery:read` | admin, provider-admin, developer, viewer, auditor |
| `hangar_discover` | `discovery:trigger` | admin, provider-admin |
| `hangar_approve`, `hangar_quarantine` | `discovery:approve` | admin, provider-admin |
| `hangar_group_list` | `group:read` | admin, provider-admin, developer, viewer |
| `hangar_group_rebalance` | `group:update` | admin, provider-admin |
| `hangar_metrics` | `metrics:read` | admin, provider-admin, viewer, auditor |
| `hangar_fetch_continuation`, `hangar_delete_continuation` | `tool:invoke` | admin, provider-admin, developer, service-account |

Check any API key or token that drives the fleet over MCP. If it worked because
MCP asked for nothing, it now needs the role its REST equivalent has always
needed. Two combinations are not guessable from the role names:

* **`provider-admin` cannot start, stop, warm, load, unload or reload.** It holds
  `mcp_servers:read` and neither `:write` nor `:lifecycle`, and not
  `config:reload`. That is deliberate and it could not perform those operations
  through the REST API either. An operator key that needs lifecycle wants `admin`
  or a custom role.
* **`developer` cannot approve, quarantine, trigger discovery, rebalance a group
  or read metrics.** It holds fleet read, write and lifecycle and none of those.

A refusal names the permission it wanted, so the log says what to grant:

```text
Not authorized to call 'hangar_stop': mcp_servers:lifecycle permission required
```

`hangar_call` is unchanged and still checks `tool:invoke` for each call in the
batch. A gateway with authentication off allows every call exactly as before, so
`--unsafe-no-auth` is unaffected.

`metrics:read` is now enforced on `hangar_metrics`. The unauthenticated
`/metrics` scrape endpoint is untouched and remains on the auth skip list.

### `front_door` now shows an operator a control plane

Additive; nothing to do. The mode served flat upstream names and no `hangar_*` to
anybody, so an operator on a front door had no management surface over MCP and
had to run a second instance in `egress` to get one.

A management tool is now listed exactly when the caller is authorized to call it,
by the same table and the same authorizer as the section above. An agent
principal sees what it saw before; an operator's list grows by what its role
permits. Nothing is shown that cannot be called, and a name that is not shown is
still answered `-32601`.

With authentication off the management surface stays empty — stricter than the
invoke path on the same gateway, deliberately: a front door that shows an
unauthenticated caller nothing today does not start showing it a control plane.

`egress` is untouched and still serves every caller the whole meta-API. There it
is not a management surface that happens to be visible, it is *the* surface: a
client without `hangar_call` reaches no upstream tool at all. See
[ADR-022](adr/ADR-022-the-management-surface-is-what-the-caller-may-call.md).

New metric: `mcp_hangar_projected_tools`, a histogram of the tools a front-door
`tools/list` returned, labelled `kind=governed|management`.

### One log line per config-file remote upstream

A `remote` server declared in `config.yaml` is outside the SSRF policy: it gets
neither the registration check that answers `400 ssrf_blocked` on the REST path,
nor the connect-time re-resolution added in 2.5.0 that closes DNS rebinding. That
exclusion is deliberate — the configuration file is trusted input, see
[ADR-021](adr/ADR-021-config-file-endpoints-outside-the-ssrf-policy.md) — and has
not changed. What changed is that startup says so, once per such upstream,
naming it and its endpoint.

Nothing is refused and no request path is affected. To have an endpoint checked,
register it through the REST API rather than the file.

## Upgrade to 2.5.3

Drop-in from 2.5.2: nothing you wrote has to change. It is six fixes, all of
them defects, and two are visible from outside the gateway — a patch number
promises they are not, so they are named here.

### `prompts/list` and `resources/list` now answer `-32601`

The gateway advertised the `prompts` and `resources` capabilities on every
deployment and served neither. Nothing hard-coded that claim: the SDK derives
each capability from whether its handler is registered, and the framework
registers both unconditionally, empty or not.

The cost was not the missing feature, it was the false statement.
`{"prompts": []}` tells a conformant client *this server has no prompts*, which
is a different thing from *this gateway does not carry prompts* — and nothing on
the wire distinguished them. A registered upstream's whole prompt and resource
surface was invisible, with no error anywhere.

| | 2.5.2 | 2.5.3 |
| --- | --- | --- |
| `initialize` capabilities | `prompts` and `resources` advertised | neither advertised |
| `prompts/list`, `resources/list` | `200` with an empty list | `-32601` Method not found |

**Who has to do anything.** A client that reads the advertised capabilities
before calling — which the specification tells it to do — sees no `prompts`
capability and does not call. Nothing to change. A client that calls these
methods unconditionally and treats a JSON-RPC error as fatal will now fail where
it previously received an empty list; it needs to check capabilities first.

This is derived rather than inverted: when the gateway proxies an upstream's
prompts and resources, the capabilities come back on their own.

### An upstream's tool catalogue may grow

The gateway never finished the MCP handshake. It sent `initialize` and went
straight to `tools/list`, skipping the `notifications/initialized` the lifecycle
requires — so every upstream, in every mode, sat permanently mid-handshake. A
server is entitled to defer work until that notification arrives, and servers
do: against the official reference server, a tool registered in its
`oninitialized` handler was neither listed nor callable through Hangar.

**What to expect.** If your upstream registers tools on initialization, this
release discovers them for the first time and its catalogue legitimately grows
after the upgrade. Anything asserting on a **tool count** will notice. Tool
**digests** are unchanged, so no existing pin moves — including pins on tools
that now carry the forwarded `title`, `annotations`, `execution`, `icons` and
`_meta`, which earlier releases discarded on the way through.

The notification is best-effort: an upstream that mishandles it produces a
warning in the log, not a failed start.

### Also in this release, with nothing to do

- The gateway identifies itself to upstreams as `mcp-hangar` at its running
  version, rather than `mcp-registry / 1.0.0` — a product name that has not
  existed for a long time. If you filter upstream logs or key server-side
  workarounds on `mcp-registry`, those match on `mcp-hangar` from now on.
- A `front_door` gateway that serves no tools now says why, at `WARNING`, and
  counts it under `mcp_hangar_empty_projection_total{reason=...}`. The three
  causes — no caller identity, nothing discovered yet, everything filtered by
  policy — used to be indistinguishable from outside.

## Upgrade to 2.5.2

Drop-in from 2.5.1: nothing you wrote has to change. It is five fixes, and the
first one decides whether a gateway starts at all.

### An auth-enabled gateway could not start on a selected storage backend

`persistence.backend` made storage one decision (ADR-019), and the branch
implementing it handed the API-key, role and tool-access-policy stores out
without creating their tables. Startup reached the auth bootstrap and died:

```
Unexpected error: relation "roles" does not exist
```

or, with no `auth.role_assignments` configured to trip that, on
`tool_access_policies` a few lines later. **Both backends were affected** --
SQLite failed the same way with `no such table: roles` -- so this was never a
PostgreSQL problem, it was the handoff.

That is the configuration [more than one replica](cookbook/25-multiple-replicas.md)
requires, so the documented multi-replica deployment could not start on 2.5.0 or
2.5.1.

**What to do: upgrade.** The tables are created when the stores are built, the
same way the event store already did it. Nothing to run by hand, and an existing
database is unaffected -- the DDL is `CREATE TABLE IF NOT EXISTS`.

If you worked around it by also naming the backend under `auth.storage:`, that
block is now redundant. It is still legal (naming the *same* backend twice
always was), so you can leave it or drop it.

### `auth bootstrap-admin` refused to run on that same configuration

The command reads the durable backend to claim the initial administrator on, and
it consulted only `auth.storage.driver` -- whose default is `memory` -- so on a
one-storage deployment it answered:

```
Error: Auth storage driver 'memory' is not durable
```

Since every `/api/auth/**` route requires an admin principal, with no carve-out
for the first call, there was no other way to mint the first key. It now uses
the backend `persistence.backend` selected.

Related, and worth knowing if you scripted around it: bootstrapping a principal
that `auth.role_assignments` also grants global admin used to fail on a
duplicate key. It no longer does.

### `provider-admin` could not deliver an egress policy

`/api/mcp_servers/{id}/l7_policy` is mapped to `policy:write`, which is what
`provider-admin` holds and why the role exists -- but the handlers demanded
`mcp_servers:write` on top, which it does not hold. The operator's push answered
403 while the `MCPEgressPolicy` CR still reported `Compiled` and
`BackstopApplied`, so **a policy enforced its network half and silently dropped
its L7 half**.

**What to check.** If you run the operator with an API key scoped to
`provider-admin`, look for `L7PushFailed` events on your `MCPEgressPolicy`
objects. If you widened that key to `admin` or `developer` to get past it, you
can narrow it back after upgrading.

### `MCP_TRUSTED_HOSTS` did not reach the MCP endpoint

It governed the REST API only. The MCP endpoint used the SDK's own
DNS-rebinding guard, built from the SDK's default bind host, so `/mcp` answered
`421 Invalid Host header` to the gateway's own Service DNS name and to every
Ingress host -- while the same names were listed in `MCP_TRUSTED_HOSTS` and
accepted by `/api/**` on the same process.

**What to check.** If you worked around this by rewriting the upstream Host at
your proxy (an nginx `upstream-vhost`, for example), you can drop that once the
hostname is in `MCP_TRUSTED_HOSTS`. Entries now match with and without a port.

One thing this does not change, and that is worth knowing when you put a Service
or an Ingress in front of a replica set: **a Streamable HTTP session lives in one
replica's memory.** A round-robin load balancer can send the second request of a
session to a pod that never saw the first. Pin it -- `sessionAffinity: ClientIP`
on the Service, or a client-address hash at the Ingress.

### `front_door` projected no tools to any tenant

`tool_access.mode: front_door` returned an **empty `tools/list` to every
authenticated tenant** over Streamable HTTP. The per-request context that
carries the caller was handed to the projection handlers and dropped, so the
resolver saw no tenant and took its deny-all branch -- correctly, for a caller it
could not identify. An empty list is indistinguishable from "no tools
configured", which is why this was quiet.

**What to check.** If you concluded that front-door mode needed a policy you had
not written yet, it did not. Per-tenant `tool_access.member` policies and
`tool_projection` withdrawals now apply as documented in
[front-door multi-tenant](cookbook/16-front-door-multi-tenant.md).

**Still not working, and not fixed here:** a *group* under front-door mode. Its
members expose the same tool names by definition, the flat projection drops any
name it finds in two servers, and so the group contributes nothing -- and takes
co-located servers sharing those names down with it. Recipe 19 pairs the two;
that combination is still open.

## Upgrade to 2.5.1

Drop-in from 2.5.0 in the sense that nothing you wrote has to change. Two things
are worth acting on rather than reading past.

### The connect-time SSRF guard was not surviving a restart

2.5.0 added a second SSRF check on every outbound connection, with the
connection pinned to the validated address, so a hostname that passed
registration could not be re-pointed at `169.254.169.254`, `10.x` or
`127.0.0.1` before the next tool call. The flag that arms it was never written
to the stored server record, so **any server rebuilt from that record came back
without it** -- after every restart, and on every replica that learned of the
registration from the shared log rather than performing it.

**What that means for a gateway running 2.5.0.** If it has restarted since a
`remote` server was registered through the REST API or by discovery, that
upstream has been reached with registration-time validation only. The endpoint
was still checked once, when it was registered; what lapsed is the re-check that
defends against the name being re-pointed afterwards. In a replica set, only the
replica that handled the registration ever had the guard.

**What to do: upgrade and restart.** The guard is restored for servers already
in the store -- no re-registration, no edit to the database. One deliberate
exception: a stored endpoint that is a private literal keeps 2.5.0's behaviour,
because such a row can only have come from discovery reporting a container
address, and arming the strict policy over it would refuse an upstream that
works today. Re-registering such a server writes the provenance that scopes the
guard correctly.

**One behaviour to expect once it is armed.** Guarding is also pinning: a
guarded connection goes to one validated address rather than letting the client
walk a multi-address DNS answer, so a dead address behind a healthy name fails
the call instead of being skipped. That shipped in 2.5.0; what changes here is
how much of your fleet it covers.

### A `coordination:` block with no `persistence.backend` is now refused

2.5.0 refused a declared cluster on a backend the replicas cannot share, and
said nothing when no backend had been selected at all. The outcome is the same
either way -- no lease keeper, every replica managing the fleet, every one
reporting `manages_fleet: true` -- so it is now refused too.

**Who is affected:** a configuration carrying `coordination:` while storage is
still configured through the legacy per-subsystem keys (`event_store.driver`,
`auth.storage.driver`). That deployment may well share one PostgreSQL, and it
was never coordinating through it. It booted on 2.5.0 and will not boot on 2.5.1
until it says where it persists:

```text
this gateway is configured as part of a cluster (`coordination:`), and no
storage backend has been selected. ... Set `persistence.backend: postgresql`,
or remove the `coordination:` block to run this as a single gateway.
```

Both ways out are in the message. A single gateway that never declared
`coordination:` is unaffected, whatever its storage.

## Upgrade to 2.5.0

**Nothing changes until you select a storage backend.** The release adds
`persistence.backend` and multi-replica coordination, and a configuration that
sets neither is unaffected -- omitting `persistence` keeps per-subsystem storage
exactly as it was. That is deliberate: a storage rewiring must not change what a
running deployment does.

Six things below apply to every deployment regardless: interpolation, the
bootstrap command, TLS, the backup endpoint, the connect-time SSRF re-check, and
the Preview header on discovery source management. Read those even if you are
not opting in -- the SSRF section in particular, since it changes a security
behaviour and describes a lapse to plan for.

### Selecting a backend takes over every persisted concern

`persistence.backend: sqlite | postgresql` chooses storage for all of it at
once: the event log and its delivery mark, server configuration, the audit
trail, saga state, approvals, API keys, roles, tool-access policies, metric
history and the management lease. A backend serves every one of them or the
selection is refused -- which is what makes the half-configured deployment
unrepresentable. Before 2.5.0 you could select the PostgreSQL auth driver and
silently lose tool-access policy management with it.

Two consequences to check before you roll out:

- **A per-subsystem key naming a different backend now refuses startup.**
  `auth.storage.driver` and `event_store.driver` are compared against your
  selection, and a contradiction fails the boot rather than being resolved by a
  precedence rule. Whichever way such a rule fell, half of what you wrote would
  be ignored -- and the half that loses is the one written most recently.
  `memory` is exempt: it is a testing choice, not a storage backend.
- **`event_store.allow_memory_fallback` no longer has anything to decide.** With
  a backend selected, the log and its delivery mark come from it, and a backend
  is durable as a whole. Keep the key if you are not selecting a backend; it
  still fails a non-durable store fast there.

**There is no migration between backends.** Selecting PostgreSQL on a gateway
that has been running on SQLite starts an empty database -- it does not move
what is in the file.

### `persistence.backend: postgresql` needs the `[postgres]` extra

A plain `pip install mcp-hangar` carries no PostgreSQL driver, so a gateway that
selects the backend without the extra fails the moment it opens a connection:
`psycopg2 is required for PostgreSQL`. Install it with the backend:

```bash
pip install "mcp-hangar[postgres]"
```

The extra used to install `asyncpg`, which nothing in the codebase imports --
the stores use `psycopg2` -- so an install that looked right still could not
start. It now installs `psycopg2-binary`. The published image installs the extra
already, so this applies to a pip install only. It applies to every replica set
too, since a `coordination:` block requires PostgreSQL.

### Selecting PostgreSQL turns coordination on, at one replica

This is the one that can surprise a single-node deployment. Coordination keys
off whether the storage **can be shared**, not off how many replicas you run, so
a single gateway on PostgreSQL takes a management lease and reports
`coordinates_with_peers: true`. It manages the fleet, because it is the holder --
nothing stops working.

What does change: **registering a `subprocess`, `docker` or `container` server
through the API is refused** (HTTP 422). Those modes attach a child process's
stdio to one gateway, and any peer that learned of such a server would start its
own copy. Servers already declared in `config.yaml` keep working -- the refusal
is on the registration path, not the startup one.

If that deployment is genuinely single-node and wants to keep registering local
modes at runtime, stay on `persistence.backend: sqlite`, which is not shareable
and therefore not coordinated.

### A declared cluster refuses a child-process server outright

The paragraph above is about *runtime registration*. Servers declared in
`config.yaml` take a different path, and when the deployment declares a
`coordination:` block they are refused **at startup**, naming every offender at
once:

```
this gateway is configured as part of a cluster (`coordination:`), and
'reports' is 'subprocess'. ... Use `remote` mode for servers several replicas
must serve, or remove the `coordination:` block to run this as a single gateway.
```

Without the block nothing here fires, which is the point of asking on that axis:
a single gateway that merely uses PostgreSQL keeps running its child processes
exactly as before.

### A `coordination:` block requires PostgreSQL

Adding `coordination:` is the statement that these replicas are meant to be
**one** gateway. On a file-backed backend it refuses to start, because replicas
that cannot share storage are not a cluster -- each would hold its own fleet and
its own lease and never notice the others. Not hypothetical: three replicas on
SQLite each reported `manages_fleet: true`, with every health check green.

Running many pods each with their own storage stays legitimate -- that is many
gateways. What is refused is calling them one.

### If you already run more than one replica

Through 2.4.0 the documentation said not to, and the failure was silent rather
than loud. To make a replica set safe on 2.5.0 you need all three of: one
PostgreSQL every replica shares, a `coordination:` block, and `remote`-mode
servers. Then check it pod by pod rather than through the Service -- exactly one
should answer `manages_fleet: true` at `GET /api/system`.

Two costs are worth knowing before the rollout rather than after: rate limits are
counted **per instance** (three replicas admit three times the configured rate --
a fleet-wide cap belongs at the ingress), and anything travelling by the shared
log reaches peers within a poll interval rather than immediately.

Full recipe: [running more than one replica](cookbook/25-multiple-replicas.md).
The decisions and their failure modes are in
[ADR-020](adr/ADR-020-high-availability.md).

### `${VAR}` is interpolated everywhere, and an unset one now fails the boot

Interpolation used to work inside `mcp_servers.<id>.auth` and nowhere else,
while the documentation described it as a property of configuration. If you kept
a secret out of the file the way the
[production checklist](cookbook/13-production-checklist.md) says to, and it
silently arrived as the literal characters `${...}`, this is why.

The refusal moved with it. A `${VAR}` with no value and no `:-default` has always
been fail-closed, and now fails the **whole boot** rather than only the `auth`
sub-block:

```
ConfigurationError: Required environment variable '${HANGAR_DB_PASSWORD}' is not
set and has no default. Use '${HANGAR_DB_PASSWORD:-default}' to provide a
default value, or '${HANGAR_DB_PASSWORD:-}' to explicitly allow an empty value.
```

So check the keys you never had to set before -- `${VAR:-}` allows an empty value
explicitly. A value that *contains* a literal `${...}`, such as a generated
password, is safe: the document is interpolated once, so substituted text is
never rescanned.

### `auth bootstrap-admin` requires `--show-key` when API keys are the only way in

On a deployment with no trusted OIDC issuer, omitting `--show-key` is refused
before anything is written:

```
Error: Nothing could use this administrator: API keys are the only
authenticator, and the key's secret would not be printed.
```

**Who is affected:** anything that scripts `mcp-hangar auth bootstrap-admin`
against a config without an `auth.oidc` block. Add `--show-key` and capture the
secret the run prints.

**Why it refuses rather than warns.** The claim is one-shot and the key it mints
is stored hashed, so a run that ends without printing the secret can be neither
repeated nor recovered from. It used to end by advising a re-run with the flag,
at the moment re-running had become impossible -- the second run answers *the
initial administrator has already been bootstrapped*, and `bootstrap-admin` is
the only subcommand in the auth CLI. The refusal costs one command; the advice
cost the deployment.

Nothing changes for a deployment that trusts an OIDC issuer: the principal
authenticates on its own identity and needs no secret. A store whose claim was
already spent with the secret discarded is recovered by clearing its
`initial_admin_bootstrap` row, or starting from a fresh auth store, and
re-running with the flag. See [recipe 12](cookbook/12-auth-rbac.md).

### Per-server TLS settings now reach the connection

`mcp_servers.<id>.tls.verify_ssl` and `tls.ca_cert_path` were accepted and
silently discarded before 2.5.0 -- the HTTP client passes an explicit transport
for retries, and the transport was built without them.

- `ca_cert_path` failing was pure loss: an upstream behind your own CA was
  unreachable with no way to fix it from configuration. It works now.
- `verify_ssl: false` failed **closed**, so it looked like a stubborn
  certificate. It now does exactly what it says. If you left that line in a
  configuration expecting it to be inert, **verification really is off now** --
  the gateway logs a warning naming the endpoint on every such upstream at
  startup. Trusting a private CA through `ca_cert_path` is verification and
  stays quiet.

### `POST /api/config/backup` answers 503 instead of 500

The backup is written beside the configuration file, so it fails wherever that
directory is not writable -- which is every deployment on the published image,
where `/app` is owned by root and the gateway runs as `hangar`. The caller used
to get `500` and `An internal server error occurred.`, with the real reason in
the log only.

It now answers `503` naming the path and the reason. Anything monitoring this
endpoint on status code should expect `503` for a filesystem refusal; mount a
writable directory and point `--config` at it if you need it to succeed.

### An endpoint registered through the API is re-checked on every connection

**Who is affected:** `remote` servers registered through the REST API or by a
discovery source. The SSRF check used to run once, at registration, against the
addresses the hostname resolved to then -- and the HTTP client then re-resolved
that name at every connect with no second check. A name that passed once could
be re-pointed at `169.254.169.254`, `10.x` or `127.0.0.1` afterwards, and every
later tool call followed it there.

Now each request on such an upstream resolves the host again, applies the same
policy the registration check used, and connects to the validated address, with
the `Host` header and the TLS SNI/certificate check still carrying the original
name. A refused address surfaces as a connection failure rather than a new error
class.

**What to do: go to 2.5.1 rather than stopping here.** On 2.5.0 this check does
not survive a restart. The record a registered server is rebuilt from does not
carry the enforcement flag, so after any restart -- and on every follower
replica in a coordinated deployment, which builds its fleet from the same
records -- those servers come back registration-time validated only, with the
connect-time guard off, and no re-registration short of
`DELETE /api/mcp_servers/<id>` plus a fresh one restores it. [2.5.1](#upgrade-to-251)
carries the flag on the record and derives it for servers registered while 2.5.0
was running, so upgrading and restarting is the whole remedy. If you are staying
on 2.5.0, the defence between restarts is the registration-time check plus a
resolver you control -- which is what 2.4.0 and earlier already ran on.

One thing does change immediately: an upstream you registered through the API
that resolves to an address the policy refuses now fails on every call, instead
of working after a registration that passed. Servers declared in `config.yaml`
are not re-checked at all, so a `remote` server deliberately pointed at an
internal address in configuration keeps connecting as before.

### Discovery source management ships as Preview

The five mutating source routes -- `POST /api/discovery/sources`, `PUT` and
`DELETE` on `/api/discovery/sources/{id}`, `POST .../scan` and `PUT
.../enable` -- now answer with a response header:

```
X-Hangar-Preview: discovery-source-management
```

It gates nothing. The routes work, no request header is required, and nothing is
refused for omitting one. It marks a surface that was broken end to end as late
as `2.5.0-rc.4` and whose behaviour may still change. The read-only discovery
flow -- listing sources, pending and quarantined servers, approve and reject --
is stable and carries no such header.

**What to do:** if you script these five, log the header rather than assert on
it, and expect their shapes to move; if you only read discovery state, nothing
changes.

## Upgrade to 2.4.0

Drop-in for a default deployment. Everything below affects deployments that run
**discovery**, which is off unless you enabled it.

### A third-party discovery source must report the addresses it found

Discovery now registers through the same command a REST caller uses, so a
discovered endpoint goes through the SSRF check. A container or pod address is
private by definition, so that check is scoped by provenance: a discovered
endpoint may resolve to a private address **only** where the container runtime
reported it for that container or pod.

The built-in sources report those addresses. A third-party source written
against the entry-point group must put them in the discovered server's metadata:

```python
metadata = {
    # ... your own metadata ...
    "runtime_addresses": ["10.88.0.7"],   # what the runtime says, never a label
}
```

Without them the source is treated as untrusted input and its servers stop
registering, with `SSRF blocked: endpoint resolves to private address` in the
log. That is the safe direction to fail, and it is a change in behaviour for a
source that used to bypass the check entirely.

Link-local, loopback and cloud metadata hostnames stay refused whatever the
runtime claims.

### Kubernetes discovery needs its client installed

```bash
pip install mcp-hangar[kubernetes]
```

The published image ships it. Before 2.4.0 the extra did not exist and the
source could not be constructed at all, so this enables a feature rather than
breaking one -- but a deployment that expected it to work silently was getting
`discovery_source_unavailable` and no servers.

### The event store now records more, and starts earlier

`EventBus.publish` persists an event that names an aggregate, where it
previously delivered without storing. Two consequences worth knowing before
you upgrade a long-running gateway:

- `data/events.db` grows where it did not before -- registrations, discoveries,
  quarantines and lifecycle transitions all land in it now.
- A server's stream begins with `McpServerRegistered` rather than with its first
  edit. Streams written before 2.4.0 keep the shape they had; nothing is
  backfilled, and replay before a stream's first row is not claimed.

Handlers must be idempotent on `event_id`. They always should have been -- the
startup sweep re-delivers anything the previous process did not finish -- but
until 2.4.0 far fewer events reached that path.

## Upgrade to 2.3.0

Drop-in for a default deployment. Two things need checking, and each affects a
narrow case: code that imports the concrete launchers from the domain layer,
and deployments running `auth.storage.driver: event_sourcing`.

> Written first against a planned 2.2.2. That release was never cut -- it became
> 2.3.0 when the launcher removal landed, so everything below ships in 2.3.0.

### The deprecated launcher import paths are gone

Only affects code importing the concrete launcher classes from the domain
layer. If you import them from `mcp_hangar.infrastructure.launchers`, which is
where they live and what the deprecation warning has said since **v1.0.2**,
nothing changes.

```python
# Both of these now raise.
from mcp_hangar.domain.services.mcp_server_launcher import DockerLauncher
from mcp_hangar.domain.services import DockerLauncher

# This is the one to use, and always was:
from mcp_hangar.infrastructure.launchers import DockerLauncher
```

The same applies to `SubprocessLauncher`, `ContainerLauncher`, `HttpLauncher`,
`ContainerConfig`, `McpServerLauncher` and `get_launcher`.

`mcp_hangar.domain.services` still exports the launcher **port**,
`IMcpServerLauncher`, along with `LaunchResult` and `TransportClient`. It is the
concrete implementations that moved out -- a domain package re-exporting
infrastructure classes is what the deprecation was about.

The shim emitted a `DeprecationWarning` on import from v1.0.2 onward, so one run
of your test suite with warnings fatal lists every call site:

```bash
python -W error::DeprecationWarning -m pytest
```

Removing it also broke a real import cycle: the domain reaching for the concrete
launchers is what forced two sagas to import their saga manager inside a
function body rather than at module level.

### If you run `auth.storage.driver: event_sourcing`, read this before you upgrade

On that driver, API keys and role assignments were written to the event store
correctly and could not be read back. The store's writer accepts any domain
event -- it serialises whatever it is handed -- while the reader looked the
class up in a table maintained by hand, which listed 30 of the 116 event types
in the codebase. All five that the API-key and role aggregates emit were
missing from it, so the first read after a restart raised
`EventSerializationError`. In practice:

- every API key stopped authenticating across a restart, and
- role assignments were invisible after a restart.

Affected from **1.2.2**, when the driver landed, through **2.2.1**. The default
driver is `memory`, and the `sqlite` and `postgresql` drivers were never
affected -- this only ever reached deployments that set `event_sourcing`
explicitly.

**No data was lost.** The events were written correctly the whole time; only the
read path failed. That is good news with a consequence worth planning for:

> Credentials and role assignments you believed were gone will start working
> again the moment you upgrade.

If you worked around the failure by re-issuing keys after each restart, the
older keys are still live and will come back. So will every role assignment ever
made on that store that was not explicitly revoked -- including `admin`.

### Check what comes back, before you upgrade

Run these against your configured `event_store.path` (default `data/events.db`):

```bash
# How much is dormant, by event type.
sqlite3 data/events.db "
  SELECT event_type, COUNT(*) FROM events
  WHERE stream_id LIKE 'api_key:%' OR stream_id LIKE 'role_assignment:%'
  GROUP BY event_type ORDER BY event_type;"

# Exactly which principals get which roles back, oldest first.
sqlite3 data/events.db "
  SELECT json_extract(data, '\$.principal_id') AS principal,
         json_extract(data, '\$.role_name')    AS role,
         event_type, created_at
  FROM events WHERE stream_id LIKE 'role_assignment:%'
  ORDER BY created_at;"
```

Revocations are events too and they replay in order, so a key or role you
revoked before the upgrade stays revoked. What returns is what was never
revoked. Revoke anything you do not want live, then upgrade.

If the counts are larger than you expect, that is the measure of how long the
store had been unreadable -- every restart since 1.2.2 left its writes behind.

### Also in this release

**Events written before the `provider` -> `mcp_server` rename replay again.**
The rename landed after 1.0.1, so an event store from 1.0.1 or earlier holds
rows typed `ProviderStarted`, `ProviderDiscovered` and so on. Replaying one was
a silent no-op: it reconstructed into the deprecated alias class, and handlers
are registered against the modern class, so it reached nothing. No error, no
warning. If you have carried an event store across that rename, expect replay to
start producing events it previously swallowed.

**A `datetime` field on a persisted event comes back as a `datetime`.** JSON has
no datetime, so it was written as an ISO string and nothing parsed it back --
consumers received a `str`. Only `PolicyPushRejected.timestamp` was affected.

Neither of these needs any configuration change.

## Upgrade to 2.2.0

**Read this one before upgrading.** Unlike 2.1.0 and 2.1.1, this is not a
drop-in release. It is a security release cut as a **minor** rather than a
patch, deliberately: three of the changes break a working deployment, two of
them silently, and `~=2.1.1`-style constraints would have pulled a patch in
unattended. Three items need action before you roll it out.

### Action required

**1. Check the role on your operator's API key.**

The compiled-egress-policy channel, `POST`/`DELETE
/api/mcp_servers/{id}/l7_policy`, now requires `policy:write` instead of
`mcp_servers:write`. `mcp_servers:write` is held by the `developer` role, so
any developer token could clear a compiled `MCPEgressPolicy` — ADR-013 makes
that channel privileged.

`provider-admin` has been given `mcp_servers:read` and `policy:write` so it is
the least-privilege home for an operator key. It previously held only the
pre-rename `provider:*` permissions, which the REST API checks against nothing,
so it could not make **any** of the operator's calls.

| Operator key role | Before 2.2.0 | From 2.2.0 |
|---|---|---|
| `admin` | works | works |
| `provider-admin` | broken (could not read servers) | **works** |
| `developer` | works | **stops delivering policy** |

If your operator key is a `developer` token, move it to `provider-admin` before
upgrading. The failure is silent otherwise: the CRD still reconciles, the status
still reports `Compiled`, and the policy never reaches the enforcement point.

**2. Check that your OPA policy returns a boolean.**

`OPAAuthorizer` compared the verdict for truthiness. A Rego rule returning an
object (`{"result": {"allow": true, ...}}`), a string (`{"result": "deny"}`) or
an array was therefore treated as **allow** — including the one that says deny.
A non-boolean verdict is now a denial (`opa_error:non_boolean_result`), and a
missing `result` key — what OPA returns for an undefined rule, e.g. a wrong
`policy_path` — is reported separately as `opa_error:undefined_result`.

If your policy returns anything other than a bare boolean, it flips from
allowing everything to denying everything. Query the rule directly and confirm
the response body is `{"result": true}` or `{"result": false}`.

**3. Check `tool_access.mode` for typos.**

An unrecognised value used to resolve to `egress` with a warning, which handed
a deployment that had written `front_door` — but misspelled it — the permissive
topology. The server now refuses to start on an invalid value. An **absent**
key still means `egress`; only a present-but-invalid one is fatal.

### Other behaviour changes

- **REST authorization is enforced on every route.** `/config`, `/discovery`,
  `/groups`, `/sessions`, `/tools`, the `/approvals` reads and the whole
  `/auth` subtree previously authenticated callers but made no authorization
  decision — any valid credential could `POST /api/auth/roles/assign` and grant
  itself `admin`. Authorization is now resolved from the route, and a route not
  in the permission table is denied. Clients that relied on the gap will start
  receiving `403`.
- **`POST /api/config/reload` no longer accepts `config_path`.** It reloads the
  server's own configuration file. A request still sending the field gets `422`
  rather than being silently ignored. Reload loads whatever path it is given and
  an `mcp_servers` entry carries `command`/`args`, so the old behaviour was a
  remote "load an arbitrary file and start what it describes" primitive.
- **Approvals pending across the upgrade will be refused.** The
  dispatch-time integrity hash moved from the redacted copy of the arguments to
  the raw ones, so records written by the old version no longer revalidate.
  Re-request them; this is the fail-closed direction.
- **An unknown `secretPatterns` group is now rejected.** A misspelled group name
  (`github-token` for `github-tokens`) used to be skipped silently, leaving the
  policy reporting as enforcing with that detector off. The policy is now
  refused at parse time, on both the operator and REST channels.
- **Approval arguments are redacted by value, not only by key name.** A secret
  under an innocuous key (`{"body": "Authorization: Bearer ..."}`) no longer
  reaches the SQLite record or the REST DTO.

### New audit events

`EgressPolicySet` and `EgressPolicyCleared` are emitted when an L7 egress policy
is attached, replaced or removed. Consumers of the event stream that enumerate
event types exhaustively should add them.

## Upgrade to 2.1.1

A drop-in security patch on 2.1.0 — no new configuration keys, no API changes.
It closes two issues found by red-teaming 2.1.0, both fail-closed:

- The L7 egress `jwt` secret pattern now catches short-header JWTs that slipped
  past the previous matcher
  ([#687](https://github.com/mcp-hangar/mcp-hangar/issues/687)).
- The approval surface is now scoped by tenant, so an approver in one tenant can
  no longer see or resolve another tenant's approvals
  ([#688](https://github.com/mcp-hangar/mcp-hangar/issues/688)).

Nothing to change in your configuration — upgrade in place.

## Upgrade to 2.1.0

Drop-in from 2.0.x for almost everyone: the new configuration keys are opt-in,
no key moved, and no API shape changed. What 2.1.0 adds is that the
human-in-the-loop approval gate is **reachable for the first time**. It was
documented, unit-tested in isolation and wired nowhere on any shipped path — no
config key could put a tool behind it, the gate service was never constructed,
and `GET /api/approvals` answered `500` while a call the policy said to hold
executed immediately ([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678),
fixed in [#684](https://github.com/mcp-hangar/mcp-hangar/pull/684)).

**The one thing that can bite: a config that already carries `approval_list`.**
The key existed on the internal policy object, so a `tools:` block naming it
parsed as a block with no access policy and the pattern was silently dropped —
those tools ran ungated. From 2.1.0 the same file is honoured: matching calls are
**held** for a human decision, for `approval_timeout_seconds` (default `300`),
and a call nobody decides is refused rather than executed. Grep your
configuration before you upgrade:

```bash
grep -rn "approval_list" /etc/mcp-hangar/
```

If a hit is not something you want gated, remove it. If it is, make sure someone
is watching `GET /api/approvals` — or a delivery adapter is installed — before
you roll it out, because otherwise every matching call now stalls for five
minutes and then fails.

Approvals are on by default and inert until a policy gates a tool. Set
`approvals: {enabled: false}` to opt out entirely.

### The server may now refuse to boot

2.1.0 adds a startup reachability check. At the end of `bootstrap()` — the funnel
`serve`, `serve --http` and the facade all pass through — it asks, for each
subsystem a configuration can demand, whether the runtime object that serves it
is actually present. A demand met by absence is no longer silent.

A tool on `approval_list` with no gate service **refuses the boot**: a gateway
that cannot hold a call is a gateway executing it unapproved, and starting anyway
is failing open. Everything else logs at `ERROR` naming the subsystem and what
asked for it. The refusal is a `ConfigurationError` reading
`Configured subsystem is not reachable on this server: ...`.

```yaml
startup_checks:
  enforce: false      # downgrade the refusals to error logs
```

There is deliberately no switch that makes an unreachable subsystem silent.

The full key reference is in
[Configuration → `tools` dual format](reference/configuration.md#tools-dual-format).

## Upgrade to 2.0.1

Drop-in from 2.0.0 — nothing to decide, no config key moved, no API shape
changed. A single security fix: the approval gate now re-establishes an
approval's validity **at dispatch** rather than only at decision, re-checking
state, expiry and the argument hash, re-resolving the effective policy, and
re-running the digest pin after the hold. Behaviour changes in one direction
only — a call whose world moved while its approval was pending (tool withdrawn,
policy tightened, arguments rewritten, approval expired) is now refused where it
previously executed. An expired approval resolves `409` instead of minting a
false `APPROVED` record ([#674](https://github.com/mcp-hangar/mcp-hangar/issues/674)).

Scope it honestly: at 2.0.1 the approval gate was **not reachable on a stock
`serve --http`** ([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678)),
so this was the guard that had to be in place before that wiring landed, not a
patch to a live exposure. The wiring landed in
[2.1.0](#upgrade-to-210), and this fix now guards a path a deployment can
actually enter.

## Upgrade to 2.0.0

MCP Hangar 2.0.0 moves the gateway onto the MCP **2026-07-28** protocol
generation and the stable `mcp==2.0.0` SDK, and it removes the last vendor
integration from core. Four things need a decision before you upgrade; the rest
is drop-in (`pip install -U mcp-hangar`, or pull
`ghcr.io/mcp-hangar/mcp-hangar:2.0.0`).

### Slack approvals need an adapter (breaking, act before upgrading)

Core no longer knows any approval vendor. The `resolve` route dropped its
`X-Slack-Signature` branch, and `delivery/slack.py` left the tree. **If your
config sets `approvals.channel: slack`, the channel silently degrades to `noop`
on 2.0.0** — approvals still queue and stay resolvable over REST, but nobody is
notified. That degradation is deliberate: refusing to boot over a notification
channel turns a degraded path into an outage.

The replacement is an adapter you run yourself. It terminates the Slack webhook,
verifies the signature, maps the Slack identity onto a Hangar principal, and
calls `POST /approvals/{id}/resolve` with an ordinary token. A reference adapter
ships in [Approval delivery adapters](guides/APPROVAL_ADAPTERS.md), which walks
the Slack case end to end — outbound notification and inbound resolution.

Why the change: both authentication branches on the old route were individually
sound, but an **unauthenticated caller chose which one ran**. One chokepoint,
one mechanism (ADR-016).

Provenance changes with it. `decided_by` was `slack:<user-id>`; it now names a
Hangar principal. Anything parsing that field — audit queries, dashboards,
exports — needs updating.

### Approval resolution is authorized now (breaking for API callers)

`approval:resolve` was defined, granted to a role, and checked nowhere: any
principal with a valid token could decide any approval given its id. It is
enforced from 2.0.0, so a caller without the permission gets `403` where it
previously got `200`.

The `x-principal-id` request header no longer sets identity. It used to be the
*only* path that set `decided_by`, including on authenticated requests, and a
client-supplied header landing in a provenance chain is not attribution.
Identity now comes from the authenticated principal; with auth disabled the
decision is attributed to the system principal.

### `tasks/result` and `tasks/list` are gone (breaking for task clients)

The task relay serves the SEP-2663 wire. `tasks/get` now **inlines** the
outcome — the round trip through `tasks/result` is what SEP-2663 removed — and
both `tasks/result` and `tasks/list` answer `-32601`. `tasks/get|update|cancel`
require the mandatory `Mcp-Name: <taskId>` header over HTTP.

The synchronous 2025-11-25 mid-flight consent flow is removed with it: Hangar no
longer issues an `elicitation/create` prompt inside `tasks/get`. On the
2026-07-28 wire the client resolves its own input by driving `tasks/update`,
which is governed and still fail-closed.

### The SDK pin moves to `mcp==2.0.0`

If your environment installs `mcp` alongside Hangar, it moves to the v2 line.
**Your upstream MCP servers do not have to.** A connection that negotiates
2025-11-25 keeps working: the handshake records the negotiated era and withholds
the modern `_meta` envelope on legacy connections.

## Upgrade to 1.6.0

MCP Hangar 1.6.0 is an observability-hardening release: tool-invocation
telemetry now follows the OpenTelemetry GenAI/MCP semantic conventions, the
transport message metrics are wired, and it ships the L7 egress-policy
([`MCPEgressPolicy`](guides/EGRESS_POLICY.md)) enforcement plane end to end.
Upgrade is drop-in (`pip install -U mcp-hangar==1.6.2`, or pull
`ghcr.io/mcp-hangar/mcp-hangar:1.6.2`); the notes below cover what changed for
telemetry consumers.

### Span attributes moved to OTel semantic conventions (breaking for trace consumers)

Tool-invocation spans now use the OTel GenAI/MCP semconv names. If you query,
filter, or alert on Hangar's traces or OTLP audit records by attribute, update:

- `mcp.tool.name` → `gen_ai.tool.name`
- `mcp.cost.input_tokens` → `gen_ai.usage.input_tokens`
- `mcp.cost.output_tokens` → `gen_ai.usage.output_tokens`
- the application span name `tool.invoke.{tool}` → `execute_tool {tool}`; the
  outgoing transport call is now a `SpanKind.CLIENT` span carrying
  `gen_ai.operation.name` and `mcp.method.name`.

The Hangar-specific governance namespaces (`mcp.enforcement.*`, `mcp.risk.*`,
`mcp.audit.*`, `mcp.cost.cents`/`model`/`currency`, `mcp.session.id`) are
unchanged. `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` are now honored.

### Metrics: new transport message metrics; three dead metrics removed

New, labeled per upstream server: `mcp_hangar_messages_sent_total`,
`mcp_hangar_messages_received_total`, and the `mcp_hangar_message_size_bytes`
histogram. **Removed** (they were never emitted): `mcp_hangar_http_connection_pool_size`,
`mcp_hangar_http_sse_streams_active`, and `mcp_hangar_http_sse_events_total` —
drop any dashboard panel or alert that still references them.

## Upgrade to 1.5.0

MCP Hangar 1.5.0 adds a one-time admin bootstrap, a configurable command-bus
rate limit, the interceptor invocation surface with phase-aware hooks,
task-lifecycle audit events, and a per-tenant discovery entry point. It also
**fixes OIDC bearer authentication over the HTTP surface**. Upgrade is drop-in
(`pip install -U mcp-hangar==1.5.0`, or pull
`ghcr.io/mcp-hangar/mcp-hangar:1.5.0`); the notes below cover the behavior
changes worth reviewing.

### OIDC bearer auth over `serve --http` now works

If you configured OIDC/JWT front-door auth (`auth.oidc`) on the HTTP server in
1.4.x and every request returned `401` with `auth_method: none` even for a valid
token, that was a header-casing bug in the JWT authenticator -- it is fixed in
1.5.0. No config change is needed; existing `auth.oidc` config now authenticates
bearer tokens as intended.

### Bootstrap the initial admin

A fresh durable auth store with anonymous access disabled could not create its
first administrator through the protected API. `mcp-hangar auth bootstrap-admin
--config PATH --principal PRINCIPAL` now grants the one-time global `admin` role
to an existing external (OIDC) principal using the server's own durable backend.
It fails closed when auth is disabled, anonymous access is allowed, or the store
is non-durable (`memory` / `event_sourcing`), and a second run is refused without
mutating storage. No secret is printed.

### Behavior changes to review

- **Tool `isError` results now count as failures.** A backend MCP tool result
  with `isError: true` is treated as a tool failure -- reflected in the per-call
  result, batch `succeeded`/`failed` counts, health, and `ToolInvocationFailed`
  events. If you previously treated error results as successes, expect failure
  counts to rise.
- **The SQLite event store fails fast.** When a durable event store cannot be
  initialized (path not writable / backend unavailable), Hangar now refuses to
  start instead of silently degrading to a non-durable in-memory store. Opt into
  the fallback with `event_store.driver: memory` or
  `event_store.allow_memory_fallback: true`. `/health/ready` returns 503 if the
  store degraded to in-memory while a durable driver was configured.
- **Group circuit breaker.** A tripped circuit breaker on one group member no
  longer blocks a healthy remaining member from serving.
- **Command-bus rate limit is configurable.** The previously-fixed command-bus
  rate limit can now be tuned in `config.yaml`; review the
  [configuration reference](reference/configuration.md) if you relied on the old
  fixed value.

## Upgrade to 1.4.0

MCP Hangar 1.4.0 builds on the 1.3 front-door release. It adds tenant-scoped
digest pins, multi-issuer OIDC trust, resource-bound JWT audiences, and
per-tenant canary routing for MCP server groups.

### Review OIDC audience binding

If `auth.oidc.resource_uri` is set, it now becomes the expected JWT `aud` value
for every trusted issuer. This aligns token validation with the RFC 9728
Protected Resource Metadata `resource` value and RFC 8707 resource indicators.

Before upgrading production front-door deployments:

- Confirm the authorization server issues tokens with `aud` equal to
  `auth.oidc.resource_uri`.
- If you need legacy audience values per issuer, leave `resource_uri` unset and
  configure `audience` on each issuer instead.
- Prefer setting `resource_uri` behind proxies; otherwise Hangar derives the
  resource from the incoming request scheme and host.

### Move multi-issuer deployments to `auth.oidc.issuers`

Single-issuer config still works:

```yaml
auth:
  oidc:
    enabled: true
    issuer: https://issuer-a.example.com
    audience: mcp-hangar
```

Use `auth.oidc.issuers` when one Hangar instance trusts multiple authorization
servers:

```yaml
auth:
  oidc:
    enabled: true
    resource_uri: https://hangar.example.com
    tenant_claim: tenant_id
    issuers:
      - issuer: https://issuer-a.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-a.example.com/jwks
      - issuer: https://issuer-b.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-b.example.com/jwks
        groups_claim: roles
```

Tokens with a missing, empty, non-string, or untrusted `iss` claim now fail
closed with a 401 instead of reaching any issuer validator.

### Add tenant-scoped digest pins intentionally

1.4.0 can enforce schema pins per tenant on the live invocation path:

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: https://payments.example.com/mcp
    tool_projection:
      digest_enforcement: block
      tenant_overrides:
        "tenant:a":
          pins:
            refund: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

`digest_enforcement` is scoped per MCP server. If unset, pin mismatches default
to `block`. Roll out pins with `audit` or `warn` first when you are recomputing
digests or onboarding a new tenant.

The deprecated `allow_degraded` unknown-tool policy is still accepted with a
`DeprecationWarning` in 1.4.0, but `allow_unverified` remains the canonical value.
Do not add new `allow_degraded` config.

### Gate canary routing by tenant identity

Group canary routing only applies when Hangar has a `tenant_id` for the caller.
Explicit tenant pins win first, then the sticky percentage split, then the
regular load-balancing strategy.

```yaml
mcp_servers:
  search:
    mode: group
    strategy: weighted_round_robin
    canary:
      member: search-v2
      split_pct: 10
      pinned_tenants:
        "tenant:beta": search-v2
    members:
      - id: search-v1
        mode: remote
        endpoint: https://search-v1.example.com/mcp
      - id: search-v2
        mode: remote
        endpoint: https://search-v2.example.com/mcp
```

Invalid canary targets are skipped with a warning. If a pinned or canary member
is not in rotation, Hangar falls back to the group load balancer instead of
routing traffic to an unhealthy member.

## Upgrade to 1.3.0

MCP Hangar 1.3.0 relicenses the project to MIT, folds the former enterprise
package into the main `mcp_hangar` package, and tightens digest-pinning
canonicalization.

### Recompute pinned tool digests

`compute_tool_digest()` now uses RFC 8785 JSON Canonicalization Scheme (JCS)
instead of `json.dumps` output. Existing pinned digests produced by earlier
versions may no longer match and must be regenerated before enforcement mode is
enabled.

When recomputing digests, note the v1.3 normalization rules:

- `None`, `{}`, `[]`, and `""` are treated as absent values.
- Tool entries with a missing, empty, or non-string `name` field are rejected.

Recommended rollout:

1. Upgrade one environment with digest enforcement set to `audit` or `warn`.
2. Collect the new expected digests from the audited tool inventory.
3. Replace old pins with the RFC 8785/JCS digests.
4. Re-enable `block` only after the audited drift is resolved.

### Rename `ALLOW_DEGRADED` to `ALLOW_UNVERIFIED`

`DigestUnknownPolicy.ALLOW_DEGRADED` was renamed to
`DigestUnknownPolicy.ALLOW_UNVERIFIED` for clarity.

If your YAML or code uses the string value `allow_degraded`, change it to
`allow_unverified`. MCP Hangar 1.3 still accepts `allow_degraded` with a
`DeprecationWarning`; 1.4.0 still accepts the alias, but new configuration should
use only `allow_unverified`.

### Remove license-tier assumptions

The former BSL/enterprise split is gone. All MCP Hangar features are now
available under the MIT license.

Required cleanup for integrations and deployment manifests:

- Stop setting `HANGAR_LICENSE_KEY`; v1.3 ignores it and emits a
  `DeprecationWarning` when present.
- Remove checks for `LicenseTier`, `LicenseValidation`, or
  `ApplicationContext.license_tier`.
- Update imports that referenced the former `enterprise/` package; auth,
  compliance, approvals, integrations, and persistence modules now live under
  `src/mcp_hangar/`.

### Verify interceptor discovery clients

`interceptors/list` now returns unique instance names required by SEP-1763:

- `mcp-hangar-validator`
- `mcp-hangar-mutator`

If a client keyed both entries by the previous shared name `mcp-hangar`, update
it to handle the two explicit instance names.
