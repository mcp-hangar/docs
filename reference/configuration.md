# Configuration Reference

All MCP Hangar behavior is controlled through a YAML configuration file and environment variables. The config file defaults to `config.yaml` in the working directory, overridden by the `MCP_CONFIG` environment variable. Environment variables take precedence over YAML settings where both exist.

## `MCP servers`

MCP Server definitions. Each key is a unique MCP server ID.

```yaml
mcp_servers:
  math:
    mode: subprocess
    command: [python, -m, math_server]
    idle_ttl_s: 300
    health_check_interval_s: 60

  my-api:
    mode: remote
    endpoint: https://api.example.com/mcp
    idle_ttl_s: 600

  my-container:
    mode: docker
    image: my-mcp:latest
    volumes:
      - ./data:/data:ro
    resources:
      memory: "512m"
      cpu: "1.0"
```

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `mode` | `str` | `"subprocess"` | subprocess, docker, remote | MCP Server mode. `container` and `podman` normalize to `docker`. |
| `command` | `list[str]` | -- | -- | Command for subprocess mode (required for subprocess) |
| `image` | `str` | -- | -- | Docker image for docker mode (required for docker) |
| `endpoint` | `str` | -- | -- | HTTP endpoint for remote mode (required for remote) |
| `env` | `dict[str, str]` | `{}` | -- | Environment variables passed to the MCP server process |
| `idle_ttl_s` | `int` | `300` | 1--86400 | Seconds of inactivity before the MCP server is auto-stopped |
| `health_check_interval_s` | `int` | `60` | 5--3600 | Interval between health checks in seconds |
| `max_consecutive_failures` | `int` | `3` | 1--100 | Consecutive health check failures before marking degraded |
| `volumes` | `list[str]` | `[]` | -- | Docker volume mounts (docker mode only) |
| `build` | `dict` | -- | -- | Docker build configuration (docker mode only) |
| `resources` | `dict` | `{memory: "512m", cpu: "1.0"}` | -- | Container resource limits (docker mode only) |
| `network` / `network_mode` | `str` | `"none"` | -- | Container network mode (docker mode only) |
| `read_only` | `bool` | `true` | -- | Read-only filesystem (docker mode only) |
| `user` | `str` | -- | -- | Container user. `"current"` maps to host `uid:gid` |
| `args` | `list[str]` | -- | -- | Container CMD override (docker mode only) |
| `description` | `str` | -- | -- | Human-readable MCP server description |
| `tools` | `list` or `dict` | -- | -- | Predefined tool schemas (list) or access policy (dict). See below. |
| `auth` | `dict` | -- | -- | HTTP auth configuration (remote mode only) |
| `tls` | `dict` | -- | -- | TLS for a `remote` upstream: `verify_ssl` (bool, default `true`) and `ca_cert_path` (a bundle to trust, for an upstream signed by your own CA). Both are honoured from 2.5.0; earlier releases accepted and discarded them |
| `http` | `dict` | -- | -- | HTTP transport configuration (remote mode only) |
| `max_concurrency` | `int` | -- | -- | Per-MCP server concurrency limit |
| `capabilities` | `dict` | -- | -- | Declared capability contract (network, filesystem, environment, tools, resources, `enforcement_mode`). Hangar enforces these at runtime and flags deviations. |

### `tools` dual format

The `tools` key accepts two formats depending on intent.

**List format** -- predefined tool schemas. The MCP server is not started to discover tools; schemas are served directly.

```yaml
mcp_servers:
  static-math:
    mode: subprocess
    command: [python, -m, math_server]
    tools:
      - name: add
        description: Add two numbers
        inputSchema:
          type: object
          properties:
            a: { type: number }
            b: { type: number }
```

**Dict format** -- tool access policy using fnmatch glob patterns.

```yaml
mcp_servers:
  restricted:
    mode: subprocess
    command: [python, -m, full_server]
    tools:
      allow_list:
        - "safe_*"
        - "read_*"
      deny_list:
        - "internal_*"
```

When `allow_list` is set, only matching tools are exposed. When only `deny_list` is set, all tools except matches are exposed.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `allow_list` | `list[str]` | `[]` | Glob patterns; when set, **only** matching tools are exposed and `deny_list` is ignored |
| `deny_list` | `list[str]` | `[]` | Glob patterns; matching tools are hidden. Wins over `approval_list` |
| `approval_list` | `list[str]` | `[]` | Glob patterns; matching tools stay visible but each call is **held for a human decision** before it runs |
| `approval_timeout_seconds` | `int` | `300` | How long a held call waits for a decision. Must be a positive integer |
| `approval_channel` | `str` | `dashboard` | A label recorded on each approval this policy holds. It does **not** choose the adapter -- one delivery is built at startup from the global `approvals.channel` and handles every approval |

The same block is accepted at every scope that takes an access policy — an
`mcp_servers` entry, a `groups` entry, a group member, and the per-tenant
`tool_access.member` block — and all four go through one parser, so a key cannot
be honoured at one scope and dropped at another.

### Holding a tool for a human (`approval_list`)

`approval_list` marks tools as visible but gated: the caller's `tools/call` is
held, an approval record is created carrying `approval_channel` as a label, and the
call runs only if a human approves it inside `approval_timeout_seconds`. A denial
or an expiry refuses the call — the gate fails closed.

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: https://payments.example.com/mcp
    tools:
      deny_list:
        - "internal_*"
      approval_list:
        - "refund_*"
        - "issue_credit"
      approval_timeout_seconds: 600
      approval_channel: dashboard
```

With that config, `list_transactions` runs straight through, `internal_reconcile`
is not exposed at all, and `refund_payment` is held for up to ten minutes while
someone decides. `deny_list` wins over `approval_list`: a tool matched by both is
hidden, not gated.

Pending approvals are listed and resolved over the REST API
(`GET /api/approvals`, `POST /api/approvals/{id}/resolve`) — see
[REST API](rest-api.md). Resolution requires the `approval:resolve` permission.
Notification is a separate concern from resolution: `dashboard` and `noop` ship
in core, and any other channel resolves from the `mcp_hangar.approvals.delivery`
entry-point group. See
[Approval delivery adapters](../guides/APPROVAL_ADAPTERS.md).

> **Before 2.1.0 this key did nothing.** `approval_list` existed on the internal
> policy object but no config parser read it, so a `tools:` block naming it
> parsed as *no access policy at all* and the matching tools ran ungated
> ([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678)). If you have such
> a block, it becomes live on upgrade — see
> [Upgrade to 2.1.0](../upgrade.md#upgrade-to-210).

The gate itself is on by default and inert until a policy gates a tool. To turn
it off:

```yaml
approvals:
  enabled: false
```

Note the interaction with [`startup_checks`](#startup_checks): disabling the gate
while a policy still names `approval_list` makes the server **refuse to boot**,
rather than start and execute those calls ungated.

## `startup_checks`

At the end of bootstrap — the funnel `serve`, `serve --http` and the facade all
pass through — Hangar checks that every subsystem the configuration *demands* is
actually reachable on the path this process took. The question asked per
subsystem is: the config demands it, and is the runtime object that serves it
present?

```yaml
startup_checks:
  enforce: true
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enforce` | `bool` | `true` | When `false`, a fail-closed subsystem that is unreachable logs at `ERROR` instead of refusing the boot |

Two outcomes:

- **Refuses the boot** — a security subsystem the config demands is absent. The
  only one today is the approval gate: a tool on `approval_list` with no gate
  service raises a configuration error reading `Configured subsystem is not
  reachable on this server: approval_gate required by tools.approval_list on
  <scope>`. A gateway that cannot hold a call is a gateway executing it
  unapproved, so starting anyway would be failing open.
- **Logs at `ERROR`** — everything else, e.g. the governed task relay enabled by
  `relay_tasks_enabled` with no governed task store. The event is
  `subsystem_configured_but_unreachable`, carrying `subsystem`, `required_by` and
  `fail_closed`.

Setting `enforce: false` downgrades the refusals to error logs. There is
deliberately no switch that makes an unreachable subsystem silent.

The approval-gate policies are read off the tool-access resolver rather than the
raw YAML, so a policy introduced by hot reload or over REST is measured the same
way as one from the config file.

## Digest Pinning

Digest pinning validates tool schemas against precomputed SHA-256 digests. Since
v1.3.0, digests are computed from RFC 8785 JSON Canonicalization Scheme (JCS)
output. Recompute existing pins after upgrading from versions that used
`json.dumps` canonicalization.

Unknown-tool handling uses `DigestUnknownPolicy` values (`block`, `warn`,
`allow_unverified`):

- `block` -- reject tools that do not have a known pinned digest.
- `warn` -- allow unknown tools and emit a warning.
- `allow_unverified` -- allow tools without a verified digest.

Mismatch handling (when a tool's schema does not match its pinned digest) uses
the separate `DigestEnforcement` levels (`audit`, `warn`, `block`):

- `audit` -- allow the mismatched tool and record the event for audit.
- `warn` -- allow the mismatched tool and emit a warning.
- `block` -- reject tools whose schema does not match the pinned digest.

`allow_degraded` was renamed to `allow_unverified` in v1.3.0. The old string is
still accepted with a `DeprecationWarning` in v1.4.0, but new configuration
should use only `allow_unverified`.

Digest computation also normalizes `None`, `{}`, `[]`, and `""` as absent values
and rejects tool entries with a missing, empty, or non-string `name` field.

Since v1.4.0, digest pins can be scoped per tenant and enforced on the live
invocation path:

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

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tool_projection.digest_enforcement` | `str` | `block` | Per-MCP server mismatch handling: `audit`, `warn`, or `block` |
| `tool_projection.tenant_overrides.<tenant>.pins` | `dict[str, str]` | `{}` | Tool name to 64-character lowercase SHA-256 digest pins for one tenant |

Tenant pins are independent per MCP server. A tenant pin only applies when the
caller identity has a matching `tenant_id`; otherwise Hangar uses the normal
projection and withdrawal logic.

## `execution`

System-wide concurrency limits.

```yaml
execution:
  max_concurrency: 50
  default_mcp_server_concurrency: 10
```

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `max_concurrency` | `int` | `50` | 0 = unlimited | System-wide maximum concurrent tool invocations |
| `default_mcp_server_concurrency` | `int` | `10` | -- | Default per-MCP server concurrency limit |

## `discovery`

Auto-discovery of MCP servers from external sources.

```yaml
discovery:
  enabled: true
  refresh_interval_s: 60
  auto_register: false
  sources:
    - type: docker
      mode: additive
    - type: filesystem
      mode: additive
      path: /etc/mcp/mcp_servers
      watch: true
```

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `enabled` | `bool` | -- | -- | Enable or disable discovery |
| `refresh_interval_s` | `int` | -- | -- | Interval between discovery scans in seconds |
| `auto_register` | `bool` | -- | -- | Automatically register discovered MCP servers |
| `sources` | `list[dict]` | `[]` | -- | Discovery source configurations (see below) |
| `security` | `dict` | -- | -- | Security constraints for discovery |
| `lifecycle` | `dict` | -- | -- | Lifecycle management for discovered MCP servers |

### `sources[]` entry

Only `type` and `mode` are read by Hangar itself. Every other key is passed to
that source's factory untouched — which is what lets a third-party source be
configured here without core knowing its option names.

`type: kubernetes` needs the Kubernetes Python client, which is an extra:
`pip install mcp-hangar[kubernetes]`. The published image ships it. Without it
Hangar starts, logs `discovery_source_unavailable`, and this source discovers
nothing.

| Key | Type | Description |
|-----|------|-------------|
| `type` | `str` | Source type: `kubernetes`, `docker`, `filesystem`, `entrypoint`, or any type registered under the `mcp_hangar.discovery_sources` entry point group. An unregistered type **fails startup** |
| `mode` | `str` | `additive` (only adds) or `authoritative` (adds and removes) |
| `path` / `pattern` | `str` | File path or glob pattern (filesystem source) |
| `watch` | `bool` | Enable file watching (filesystem source) |
| `socket_path` | `str` | Docker/Podman socket (docker source) |
| `namespaces` | `list[str]` | Kubernetes namespaces to scan |
| `label_selector` | `str` | Kubernetes label selector |
| `in_cluster` | `bool` | Use in-cluster Kubernetes config |
| `allowed_namespaces` | `list[str]` | Kubernetes namespace allowlist; empty means "everything not denied" |
| `denied_namespaces` | `list[str]` | Kubernetes namespace denylist, default `[kube-system, default]`. Wins over the allowlist |
| `group` | `str` | Target group for discovered MCP servers |

### `security` sub-section

Constraints applied to every source, whatever it discovers.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `allowed_namespaces` | `list[str]` | -- | **Deprecated** — moved to the kubernetes source entry above. Still honoured, and logs `discovery_namespace_policy_deprecated_location`; the source's own setting wins when both are present |
| `denied_namespaces` | `list[str]` | -- | **Deprecated** — see `allowed_namespaces` |
| `require_health_check` | `bool` | -- | Require health check before registration |
| `require_mcp_schema` | `bool` | -- | Require valid MCP schema |
| `max_mcp_servers_per_source` | `int` | -- | Maximum MCP servers per source |
| `max_registration_rate` | `int` | -- | Registration rate limit |
| `health_check_timeout_s` | `float` | -- | Health check timeout in seconds |
| `quarantine_on_failure` | `bool` | -- | Quarantine MCP servers that fail health checks |

### `lifecycle` sub-section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_ttl_s` | `int` | -- | Default TTL for discovered MCP servers |
| `check_interval_s` | `int` | -- | Lifecycle check interval in seconds |
| `drain_timeout_s` | `int` | -- | Drain timeout before removal |

## `retry`

Retry policy for failed operations.

```yaml
retry:
  default_policy:
    max_attempts: 3
    backoff: exponential
    initial_delay: 1.0
    max_delay: 30.0
    retry_on:
      - ConnectionError
      - TimeoutError
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_policy.max_attempts` | `int` | -- | Maximum retry attempts |
| `default_policy.backoff` | `str` | -- | Backoff strategy (e.g., `exponential`) |
| `default_policy.initial_delay` | `float` | -- | Initial delay in seconds |
| `default_policy.max_delay` | `float` | -- | Maximum delay in seconds |
| `default_policy.retry_on` | `list[str]` | -- | Exception types to retry on |

## `event_store`

Persist domain events for audit and replay.

```yaml
event_store:
  enabled: true
  driver: sqlite
  path: data/events.db
  allow_memory_fallback: false
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | -- | Enable event persistence |
| `driver` | `str` | -- | Storage driver: `sqlite` or `memory` |
| `path` | `str` | -- | SQLite database path (sqlite driver only) |
| `allow_memory_fallback` | `bool` | `false` | Permit degrading to an in-memory store when a durable driver cannot initialize, instead of refusing to start |

### Durable-store fail-fast

When a durable driver (`sqlite`) cannot initialize its store -- for example the
`path` is not writable -- Hangar **refuses to start** rather than silently
degrading to a non-durable in-memory store. To opt into the fallback, set
`driver: memory` or `allow_memory_fallback: true`.

If the store degrades to in-memory while a durable driver was configured,
`/health/ready` returns **503** (the process stays live, but reports not-ready)
so an orchestrator does not route traffic to an instance that is silently
dropping its audit trail.

## `persistence`

*Since 2.5.0.* One storage decision for everything the gateway keeps: the event
log and its delivery mark, server configuration, the audit trail, saga state,
approvals, API keys, roles, tool-access policies, metric history and the
management lease.

```yaml
persistence:
  backend: postgresql
  postgresql:
    host: db.internal.example
    port: 5432
    user: hangar
    password: ${HANGAR_DB_PASSWORD}
    database: mcp_hangar
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `backend` | `str` | -- | `sqlite` or `postgresql`. Omit the block entirely and each subsystem configures its own storage as before |
| `<backend name>` | `map` | -- | Passed to that backend untouched. `data_dir` means nothing to PostgreSQL and `host` means nothing to SQLite |

The block under the backend's own name is handed to its factory as-is, so the
two never have to know each other's vocabulary.

**A backend serves every concern or it is refused.** Selection checks all of
them and names every missing one at once. A backend cannot be half-configured:
that is what made it possible to select PostgreSQL and silently lose
tool-access policy management before 2.5.0.

**A contradiction is refused rather than resolved.** Selecting a backend while
a legacy per-subsystem key names a different one fails at startup. Every
precedence rule silently ignores half of what you wrote, and the half that
loses is the one you wrote most recently. `memory` is exempt -- it is a testing
choice rather than a storage backend.

**Which one to choose.** `sqlite` is the standalone answer: files under one
directory, nothing to install, nothing to run, and not shareable between
processes. `postgresql` is the only one several gateways can share, and is
therefore required for more than one replica -- see `coordination` below and
[Running more than one replica](../cookbook/25-multiple-replicas.md).

**`postgresql` needs its driver installed.** `psycopg2` is an extra rather than
a base dependency -- `pip install mcp-hangar[postgres]`. The published image
ships it, so image and chart deployments are unaffected; a plain
`pip install mcp-hangar` is not, and the first connection raises `psycopg2 is
required for PostgreSQL`.

No migration is provided between backends. Selecting PostgreSQL on a gateway
that has been running on SQLite starts an empty database.

## `coordination`

*Since 2.5.0.* Declares that these replicas are meant to be **one** gateway
rather than several independent ones. Present only for multi-replica
deployments.

```yaml
coordination:
  lease_ttl_s: 15
  renew_interval_s: 5
  renew_deadline_s: 10
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lease_ttl_s` | `float` | `15.0` | How long a management tenure lasts without renewal |
| `renew_interval_s` | `float` | `5.0` | How often the holder renews, and how often a follower retries |
| `renew_deadline_s` | `float` | `10.0` | How long this instance will go without a *successful* renewal before it gives the lease up on its own. Must be under `lease_ttl_s` |

The defaults mirror Kubernetes leader election. Shorter values replace a dead
leader sooner and make a garbage-collection pause likelier to cost a live one
its lease; a fleet whose manager keeps changing converges worse than one whose
manager is occasionally slow.

`renew_deadline_s` is deliberately under the TTL. An unreachable database is
not an answer: the tenure expires on its clock whether or not this instance can
read it, so the instance gives up slightly early rather than slightly late.

**This block requires a shareable backend.** Configuring it with `sqlite`
refuses to start, because replicas that cannot share storage are not a cluster
-- each would hold its own fleet and its own lease and they would never notice
each other. Either use `postgresql`, or remove the block to run this as a
single gateway.

## `logging`

Log output configuration.

```yaml
logging:
  level: INFO
  json_format: false
  file: /var/log/mcp-hangar.log
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `level` | `str` | `"INFO"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `json_format` | `bool` | `false` | Enable structured JSON logging |
| `file` | `str` | -- | Log file path |

## `observability`

Tracing and LLM observability integrations.

### `tracing` sub-section

```yaml
observability:
  tracing:
    enabled: true
    otlp_endpoint: http://localhost:4317
    service_name: mcp-hangar
    console_export: false
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | -- | Enable OpenTelemetry tracing |
| `otlp_endpoint` | `str` | `"http://localhost:4317"` | OTLP exporter endpoint |
| `service_name` | `str` | `"mcp-hangar"` | Service name for traces |
| `jaeger_host` | `str` | -- | Jaeger agent host |
| `jaeger_port` | `int` | `6831` | Jaeger agent port |
| `console_export` | `bool` | -- | Export traces to console (development) |

### `langfuse` sub-section

```yaml
observability:
  langfuse:
    enabled: true
    public_key: pk-lf-...
    secret_key: ${LANGFUSE_SECRET_KEY}
    host: https://cloud.langfuse.com
    sample_rate: 1.0
    scrub_inputs: true
    scrub_outputs: true
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `false` | Enable Langfuse LLM observability |
| `public_key` | `str` | -- | Langfuse public API key |
| `secret_key` | `str` | -- | Langfuse secret key. Supports env var interpolation: `${LANGFUSE_SECRET_KEY}` |
| `host` | `str` | `"https://cloud.langfuse.com"` | Langfuse API host |
| `sample_rate` | `float` | `1.0` | Trace sampling rate (0.0--1.0) |
| `scrub_inputs` | `bool` | **`true`** | Redact sensitive data from tool inputs. On by default -- set it to `false` to send raw arguments to Langfuse |
| `scrub_outputs` | `bool` | **`true`** | Redact sensitive data from tool outputs. On by default |

## `auth`

Authentication and authorization.

```yaml
auth:
  enabled: true
  allow_anonymous: false
  api_key:
    enabled: true
    header_name: X-API-Key
  oidc:
    enabled: false
    issuer: https://auth.example.com
    audience: mcp-hangar
    resource_uri: https://hangar.example.com
    issuers:
      - issuer: https://issuer-a.example.com
        audience: https://hangar.example.com
        jwks_uri: https://issuer-a.example.com/jwks
  rate_limit:
    enabled: true
    max_attempts: 10
    window_seconds: 60
    lockout_seconds: 300
```

> **Note:** The `auth.rate_limit` block above configures login-attempt lockout
> (failed authentication throttling), distinct from the runtime command-bus
> token-bucket limiter that throttles command dispatch.

Since 1.5.0 the command-bus token-bucket limiter is configurable via a top-level
`rate_limit` block; its values take precedence over the `MCP_RATE_LIMIT_RPS` /
`MCP_RATE_LIMIT_BURST` environment variables (which remain a fallback). Omit the
block to keep the env/default behavior (10 rps, burst 20):

```yaml
rate_limit:
  rps: 10     # tokens refilled per second (default 10)
  burst: 20   # burst capacity / bucket size (default 20)
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | -- | Enable authentication |
| `allow_anonymous` | `bool` | -- | Allow unauthenticated requests |
| `api_key.enabled` | `bool` | -- | Enable API key authentication |
| `api_key.header_name` | `str` | -- | HTTP header name for API key |
| `oidc.enabled` | `bool` | -- | Enable OpenID Connect authentication |
| `oidc.issuer` | `str` | -- | OIDC issuer URL |
| `oidc.audience` | `str` | -- | Expected token audience |
| `oidc.resource_uri` | `str` | -- | Public resource URI. When set, this is advertised in RFC 9728 metadata and enforced as JWT `aud` for all issuers. |
| `oidc.issuers` | `list[dict]` | `[]` | Multi-issuer trust entries. When non-empty, these override the legacy top-level `oidc.issuer`. |
| `oidc.issuers[].issuer` | `str` | inherited | Trusted OIDC issuer URL |
| `oidc.issuers[].audience` | `str` | inherited | Expected audience when `resource_uri` is unset |
| `oidc.issuers[].jwks_uri` | `str` | inherited | JWKS endpoint for this issuer |
| `oidc.issuers[].client_id` | `str` | inherited | Optional client ID for additional validation |
| `oidc.issuers[].max_token_lifetime_seconds` | `int` | inherited | Maximum JWT lifetime for this issuer; `0` disables the check |
| `oidc.subject_claim` | `str` | -- | JWT subject claim field |
| `oidc.groups_claim` | `str` | -- | JWT groups claim field |
| `oidc.email_claim` | `str` | -- | JWT email claim field |
| `oidc.tenant_claim` | `str` | -- | JWT tenant claim field |
| `opa.enabled` | `bool` | -- | Enable Open Policy Agent authorization |
| `opa.url` | `str` | -- | OPA server URL |
| `opa.policy_path` | `str` | -- | OPA policy path |
| `opa.timeout` | `float` | -- | OPA request timeout in seconds |
| `storage` | `dict` | -- | Auth storage configuration (driver, path, host, etc.) |
| `rate_limit` | `dict` | -- | Auth-specific rate limiting |
| `role_assignments` | `list[dict]` | -- | Role assignment rules |

## `config_reload`

Hot-reload configuration. See the [Hot-Reload Reference](hot-reload.md) for full details.

```yaml
config_reload:
  enabled: true
  use_watchdog: true
  interval_s: 5
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | -- | Enable automatic config file watching |
| `use_watchdog` | `bool` | -- | Use watchdog library for file system events |
| `interval_s` | `int` | -- | Polling interval in seconds (fallback when watchdog unavailable) |

## `groups`

MCP Server groups are configured inside the `MCP servers` section with `mode: group`. A group load-balances requests across multiple member MCP servers.

```yaml
mcp_servers:
  llm-group:
    mode: group
    strategy: round_robin
    min_healthy: 1
    auto_start: true
    description: LLM mcp_server pool
    health:
      unhealthy_threshold: 2
      healthy_threshold: 1
    circuit_breaker:
      failure_threshold: 10
      reset_timeout_s: 60.0
    tools:
      allow_list: ["generate_*"]
    canary:
      member: llm-2
      split_pct: 10
      pinned_tenants:
        "tenant:beta": llm-2
    members:
      - id: llm-1
        mode: subprocess
        command: [python, -m, llm_server]
        weight: 70
        priority: 1
      - id: llm-2
        mode: subprocess
        command: [python, -m, llm_server]
        weight: 30
        priority: 2
```

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `mode` | `str` | -- | `"group"` | Must be `"group"` |
| `strategy` | `str` | `"round_robin"` | round_robin, weighted_round_robin, least_connections, random, priority | Load balancing strategy |
| `min_healthy` | `int` | `1` | >= 1 | Minimum healthy members for group HEALTHY state |
| `auto_start` | `bool` | `true` | -- | Auto-start members when the group is created |
| `description` | `str` | -- | -- | Group description |
| `health.unhealthy_threshold` | `int` | `2` | >= 1 | Consecutive failures before removing member from rotation |
| `health.healthy_threshold` | `int` | `1` | >= 1 | Consecutive successes before re-adding member to rotation |
| `circuit_breaker.failure_threshold` | `int` | `10` | >= 1 | Total group failures before the circuit opens |
| `circuit_breaker.reset_timeout_s` | `float` | `60.0` | >= 1.0 | Seconds before the circuit auto-resets |
| `tools` | `dict` | -- | -- | Group-level tool access policy (`allow_list`, `deny_list`, `approval_list`, `approval_timeout_seconds`, `approval_channel`) -- see [`tools` dual format](#tools-dual-format) |
| `canary.member` | `str` | -- | -- | Member that receives canary split traffic |
| `canary.split_pct` | `int` | `0` | 0--100 | Deterministic percentage of tenants routed to `canary.member` |
| `canary.pinned_tenants` | `dict[str, str]` | `{}` | -- | Tenant ID to member ID pins; explicit pins win over split routing |
| `members` | `list[dict]` | `[]` | -- | Member MCP server configurations |

### Member configuration

Each member entry supports all standard MCP server keys (`mode`, `command`, `image`, `endpoint`, `env`, etc.) plus:

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `id` | `str` | -- | -- | Unique member ID (required) |
| `weight` | `int` | -- | 1--100 | Weight for weighted_round_robin and random strategies |
| `priority` | `int` | -- | 1--100 | Priority for priority strategy (lower number = higher priority) |
| `tools` | `dict` | -- | -- | Member-level tool access policy, same keys as the group-level block |

## Environment Variables

Environment variables override corresponding YAML settings. Variables follow the `MCP_` prefix convention. Third-party integrations (OpenTelemetry, Langfuse, Jaeger) use their standard prefixes.

### Server / CLI

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_CONFIG` | `"config.yaml"` | Path to YAML configuration file |
| `MCP_MODE` | `"stdio"` | Server mode: `stdio` or `http` |
| `MCP_HTTP_HOST` | `"0.0.0.0"` | HTTP bind host |
| `MCP_HTTP_PORT` | `8000` | HTTP bind port |
| `MCP_LOG_LEVEL` | `"INFO"` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MCP_JSON_LOGS` | `"false"` | Enable structured JSON logging |

### Security / Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_RATE_LIMIT_RPS` | `"10"` | Rate limit: requests per second |
| `MCP_RATE_LIMIT_BURST` | `"20"` | Rate limit: burst size |
| `MCP_ALLOW_ABSOLUTE_PATHS` | `"false"` | Allow absolute paths in input validation |

### Persistence

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PERSISTENCE_ENABLED` | `"false"` | Enable state persistence |
| `MCP_DATABASE_PATH` | `"data/mcp_hangar.db"` | SQLite database file path |
| `MCP_DATABASE_WAL` | `"true"` | Enable WAL mode for SQLite |
| `MCP_AUTO_RECOVER` | `"true"` | Auto-recover persisted state on startup |
| `HANGAR_INSTANCE_LABEL` | hostname | *Since 2.5.0.* Prefix for this instance's identity, which appears on every event it produces. Under Kubernetes, set it from the downward API (`metadata.name`); the hostname is that same pod name, which is why it is the fallback. It is a **label**, not the identity: a per-process suffix is always appended, so replicas rolled from one ConfigMap cannot end up sharing an id |

### Observability / Tracing

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRACING_ENABLED` | `"true"` | Enable OpenTelemetry tracing |
| `MCP_TRACING_CONSOLE` | from config | Enable console trace export |
| `MCP_ENVIRONMENT` | `"development"` | Deployment environment label |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `"http://localhost:4317"` | OTLP exporter endpoint |
| `OTEL_SERVICE_NAME` | `"mcp-hangar"` | OpenTelemetry service name |
| `JAEGER_HOST` | -- | Jaeger agent host |
| `JAEGER_PORT` | `6831` | Jaeger agent port |

### Langfuse

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_LANGFUSE_ENABLED` | `"false"` | Enable Langfuse LLM observability |
| `LANGFUSE_PUBLIC_KEY` | -- | Langfuse public API key |
| `LANGFUSE_SECRET_KEY` | -- | Langfuse secret key (sensitive) |
| `LANGFUSE_HOST` | `"https://cloud.langfuse.com"` | Langfuse API host |
| `MCP_LANGFUSE_SAMPLE_RATE` | `"1.0"` | Trace sampling rate (0.0--1.0) |
| `MCP_LANGFUSE_SCRUB_INPUTS` | `"false"` | Redact sensitive tool inputs |
| `MCP_LANGFUSE_SCRUB_OUTPUTS` | `"false"` | Redact sensitive tool outputs |

!!! note "Legacy `HANGAR_*` prefix"
    The following legacy variables are supported for backward compatibility but `MCP_*` is the canonical prefix:
    `HANGAR_LANGFUSE_ENABLED` maps to `MCP_LANGFUSE_ENABLED`,
    `HANGAR_LANGFUSE_SAMPLE_RATE` maps to `MCP_LANGFUSE_SAMPLE_RATE`,
    `HANGAR_LANGFUSE_SCRUB_INPUTS` maps to `MCP_LANGFUSE_SCRUB_INPUTS`,
    `HANGAR_LANGFUSE_SCRUB_OUTPUTS` maps to `MCP_LANGFUSE_SCRUB_OUTPUTS`.

### Deprecated Variables

`HANGAR_LICENSE_KEY` is deprecated in v1.3.0. MCP Hangar ignores it and emits a
`DeprecationWarning` when the variable is set. Remove it from deployment
manifests; MCP Hangar is MIT-licensed and no longer uses license keys.

License-tier configuration and API fields were removed in v1.3.0. Remove any
custom deployment checks for `license_tier`, `LicenseTier`, or
`ApplicationContext.license_tier`.

### Container Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_CONTAINER_RUNTIME` | -- | Force container runtime (`docker` or `podman`) |
| `MCP_CI_RELAX_VOLUME_PERMS` | -- | Relax volume permission checks in CI environments |
| `MCP_CONTAINER_INHERIT_STDERR` | -- | Inherit stderr from container processes |

### Auth

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_JWT_MAX_TOKEN_LIFETIME` | -- | Maximum JWT token lifetime |
