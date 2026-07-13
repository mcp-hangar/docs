# 20 -- Local Dev & Staging Profiles

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md), [12 -- Auth & RBAC](12-auth-rbac.md)
> **You will need:** Python 3.11+, `pip install mcp-hangar==1.4.0`
> **Time:** 20 minutes
> **Adds:** Two ready-to-run `config.yaml` profiles -- a loopback dev profile and an auth-on staging profile

## The Problem

You want to iterate quickly on your own machine with auth off and verbose
logs, then validate a build in staging that looks much closer to production --
authentication on, discovery enabled, telemetry flowing -- without hand-editing
one shared config every time you switch. You also need a clear line for where
"staging" stops and "production" begins, so nobody ships a demo config to prod.

This recipe gives you two complete, copy-pasteable profiles and the exact
command to run each. Every config field, env var, command, and endpoint below
is verified against MCP Hangar core **1.4.0** (`pip install mcp-hangar==1.4.0`).

> **Neither profile is production-ready.** The dev profile has no auth. The
> staging profile turns auth on but stops short of the production trust
> boundary (TLS termination, an OIDC front door, secret management, hardened
> discovery). See [What's Next](#whats-next) for the companions that cross that
> line.

## Profile A -- Local development (`config.dev.yaml`)

Optimize for fast iteration: bind loopback only, leave auth off, log at `DEBUG`,
and run one deterministic subprocess provider so you can verify a tool call
without any network dependency.

```yaml
# config.dev.yaml -- Recipe 20: local development profile
mcp_servers:
  # Deterministic, no-network provider: the bundled example math server.
  # `add` returns a fixed result, so verification is reproducible.
  math:
    mode: subprocess
    command: [python, -m, examples.provider_math.server]
    idle_ttl_s: 180

# Local event persistence so you can inspect the audit trail across restarts.
event_store:
  enabled: true
  driver: sqlite            # sqlite | memory
  path: data/dev-events.db

logging:
  level: DEBUG              # verbose for iteration
  json_format: false        # human-readable console logs

# No `auth:` section -> auth is off. This is only safe on a loopback bind
# (see the run command below). Hangar refuses a non-loopback bind without auth.
```

Run it in HTTP mode, bound to loopback, with verbose output:

```bash
mcp-hangar --config config.dev.yaml serve --http --host 127.0.0.1 --port 8000 --verbose
```

For a stdio session (e.g. Claude Desktop) drop the HTTP flags:

```bash
mcp-hangar --config config.dev.yaml serve
```

Verify MCP reachability and one deterministic tool call:

```bash
# Liveness -- no auth needed on loopback
curl -s http://127.0.0.1:8000/health/live

# Start the provider, then invoke the deterministic `add` tool
curl -s -X POST http://127.0.0.1:8000/api/mcp_servers/math/start
curl -s -X POST http://127.0.0.1:8000/api/mcp_servers/math/tools/add \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"a": 2, "b": 3}}'
```

`add` always returns `5` for `{a: 2, b: 3}`, so this call is a reproducible
smoke test. Confirm local event persistence survived the call:

```bash
ls -l data/dev-events.db          # SQLite file exists and grows
curl -s http://127.0.0.1:8000/health/ready   # 200 = event store durable
```

> **Why loopback matters.** With no `auth:` section, Hangar starts on
> `127.0.0.1`, `::1`, or `localhost` but **refuses** a non-loopback bind and
> logs `http_auth_required_for_non_loopback`. The `--unsafe-no-auth` override
> exists but is exactly what staging and production must never use.

## Profile B -- Staging (`config.staging.yaml`)

Move closer to production: turn API-key authentication on, enable Docker
discovery in additive mode, keep durable event persistence, and switch to
structured logs so a telemetry collector can parse them. Rate limiting is set
explicitly rather than left to defaults.

```yaml
# config.staging.yaml -- Recipe 20: staging profile
mcp_servers:
  math:
    mode: subprocess
    command: [python, -m, examples.provider_math.server]
    idle_ttl_s: 180

# Authentication ON. API keys are minted at runtime via the REST API
# (see Recipe 12); do NOT bake a key into this file.
auth:
  enabled: true
  allow_anonymous: false
  api_key:
    enabled: true
    header_name: X-API-Key

# Topology posture. `egress` (the default) treats callers as trusted back-end
# clients. `front_door` is for the multi-tenant OIDC edge -- out of scope here.
tool_access:
  mode: egress              # egress | front_door

# Additive discovery: detect providers, but never let discovery remove the
# static ones above. Requires manual approval of discovered servers.
discovery:
  enabled: true
  refresh_interval_s: 30
  auto_register: false
  sources:
    - type: docker          # docker | kubernetes | filesystem | entrypoint
      mode: additive         # additive | authoritative

# Explicit rate limit rather than the 10 rps / burst 20 default.
rate_limit:
  rps: 20
  burst: 40

event_store:
  enabled: true
  driver: sqlite
  path: data/staging-events.db
  allow_memory_fallback: false   # fail fast if the DB path is not durable

logging:
  level: INFO
  json_format: true          # structured logs for the collector
```

Run it with structured logs. Tracing to your OTLP collector is toggled by
environment variables, so it stays out of the committed config:

```bash
export MCP_TRACING_ENABLED=true
export MCP_ENVIRONMENT=staging
mcp-hangar --config config.staging.yaml serve --http --host 0.0.0.0 --port 8000 --json-logs
```

Validate the staging auth and reversible-operation path without any privileged
production credential:

```bash
# 1. Unauthenticated request is rejected
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/mcp_servers   # -> 401

# 2. Mint a scoped API key (raw key is shown once -- capture it)
curl -s -X POST http://localhost:8000/api/auth/keys \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "service:staging-smoke", "name": "Staging Smoke"}'

# 3. Authenticated request succeeds
curl -s -H "X-API-Key: <raw_key>" http://localhost:8000/api/mcp_servers   # -> 200

# 4. Reversible operation: start then stop a provider, no state left behind
curl -s -H "X-API-Key: <raw_key>" -X POST http://localhost:8000/api/mcp_servers/math/start
curl -s -H "X-API-Key: <raw_key>" -X POST http://localhost:8000/api/mcp_servers/math/stop
```

Verify telemetry and durable persistence:

```bash
# Prometheus metrics are always exposed in HTTP mode
curl -s http://localhost:8000/metrics | grep mcp_hangar_tool_calls_total

# Readiness reflects event-store durability (503 if durability was lost)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health/ready
```

If `MCP_TRACING_ENABLED=true` and your OTLP endpoint is reachable, spans for
each tool call are exported; set `MCP_TRACING_CONSOLE=true` to also print them
for a quick local check.

## What Just Happened

The two files differ only where the environment differs:

| Concern | `config.dev.yaml` | `config.staging.yaml` |
| --- | --- | --- |
| Auth | none (`auth:` omitted) | `auth.enabled: true`, `allow_anonymous: false` |
| Bind | `127.0.0.1` (loopback) | `0.0.0.0` (auth required) |
| Discovery | off | `discovery.enabled: true`, Docker source, additive |
| Rate limit | default (10 rps / burst 20) | explicit `rate_limit.rps: 20` / `burst: 40` |
| Logs | `DEBUG`, human-readable | `INFO`, `json_format: true` |
| Tracing | off | `MCP_TRACING_ENABLED=true` to a collector |
| Event store | `sqlite` @ `data/dev-events.db` | `sqlite` @ `data/staging-events.db` |

The provider list is intentionally identical: the same deterministic `math`
server verifies in both profiles, so a difference in behavior points at the
profile, not the workload.

## Promotion Checklist (dev -> staging)

- [ ] Provider verified in dev via the deterministic `add` call
- [ ] `auth.enabled: true` and `auth.allow_anonymous: false` set in staging
- [ ] A scoped API key minted at runtime (never committed to the config)
- [ ] Bind moved off loopback only because auth is on (no `--unsafe-no-auth`)
- [ ] `discovery.auto_register: false` so discovered servers need approval
- [ ] `event_store.allow_memory_fallback: false` so a non-durable store fails fast
- [ ] `logging.json_format: true` and `MCP_TRACING_ENABLED=true` for the collector
- [ ] `/health/ready` returns `200` and `/metrics` is scraped

## Teardown & Secret Cleanup

```bash
# Stop any running providers, then Ctrl-C the server
curl -s -X POST http://localhost:8000/api/mcp_servers/math/stop

# Revoke every API key you minted for the smoke test
curl -s -H "X-API-Key: <raw_key>" http://localhost:8000/api/auth/keys        # list key_ids
curl -s -H "X-API-Key: <raw_key>" -X DELETE http://localhost:8000/api/auth/keys/<key_id>

# Clear the local event stores and unset any exported secrets
rm -f data/dev-events.db data/staging-events.db
unset MCP_TRACING_ENABLED MCP_ENVIRONMENT
```

Any raw key printed to your terminal is a secret -- clear the scrollback if you
pasted one, and never commit it. The staging profile deliberately ships **no**
default credential.

## Key Config Reference

| Key / Var | Where | Description |
| --- | --- | --- |
| `auth.enabled` | config | Turn authentication on (default `false`) |
| `auth.allow_anonymous` | config | Allow unauthenticated requests (default `false`) |
| `auth.api_key.header_name` | config | Header carrying the API key (default `X-API-Key`) |
| `tool_access.mode` | config | `egress` (default) or `front_door` |
| `discovery.sources[].type` | config | `docker`, `kubernetes`, `filesystem`, `entrypoint` |
| `discovery.sources[].mode` | config | `additive` or `authoritative` |
| `event_store.driver` | config | `sqlite` or `memory` |
| `event_store.allow_memory_fallback` | config | Accept a non-durable store (default `false`) |
| `rate_limit.rps` / `rate_limit.burst` | config | Token-bucket refill and size |
| `MCP_TRACING_ENABLED` | env | Enable OpenTelemetry tracing (default `true`) |
| `MCP_TRACING_CONSOLE` | env | Also print spans to the console |
| `MCP_ENVIRONMENT` | env | `deployment.environment` resource attribute |
| `MCP_RATE_LIMIT_RPS` / `MCP_RATE_LIMIT_BURST` | env | Rate-limit fallback when `rate_limit:` is omitted |
| `--config <path>` | CLI | Select the profile file |
| `--verbose` / `--json-logs` | CLI | Debug output / structured logs |
| `--unsafe-no-auth` | CLI | Override the non-loopback auth guard (never in staging/prod) |

## What's Next

You have a dev loop and a staging validation. The remaining companions in the
Deployment Playbook ([mcp-hangar/docs#17](https://github.com/mcp-hangar/docs/issues/17))
cross the production boundary this recipe deliberately stops short of:

- **Production boundaries** ([mcp-hangar/docs#19](https://github.com/mcp-hangar/docs/issues/19)) --
  exactly what must change before staging becomes production.
- **OIDC front door** ([mcp-hangar/docs#20](https://github.com/mcp-hangar/docs/issues/20)) --
  the `tool_access.mode: front_door` edge with real identity, built on
  [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md).
- **Production Checklist** -- run [13 -- Production Checklist](13-production-checklist.md)
  before you promote anything past staging.
