# Progressive Deployment Playbook

This is the umbrella guide for taking MCP Hangar from a laptop to an
internet-facing, authenticated gateway. It is a **maturity model**: each stage
adds exactly one class of guarantee on top of the previous one, so you never
turn on production controls before you have a working baseline to compare
against.

Read this guide top to bottom to understand the progression and the decision
points. Then follow the companion recipes for the copy-pasteable configs at
each stage.

## Audience

Operators who already have a single MCP server working behind Hangar (see
[Cookbook 01 -- HTTP Gateway](../cookbook/01-http-gateway.md)) and now need to
promote that setup through staging to production without guessing which knobs
matter at which stage.

## The Maturity Model

Hangar deployments move through four stages. Each row is a superset of the one
above it -- you keep everything from the previous stage and add the new column.

| Stage | Trust boundary | Auth | Tool surface | Durability |
| --- | --- | --- | --- | --- |
| Local dev | Your machine only | Off | Full `hangar_*` meta-API | In-memory OK |
| Staging | Trusted internal callers | On, internal keys | Full `hangar_*` meta-API | Durable event store |
| Production read-only | Internal, least-privilege | On, RBAC | Curated, read-only tools | Durable + backups |
| External front door | Untrusted external agents | OIDC, per-tenant | Flat per-tenant tools | Durable + backups |

The single most important idea: **the topology mode and the auth posture are
the boundary**, not the network. A staging box on a private subnet with auth off
is not "internally safe" -- it is one misrouted route away from being open.
Treat each stage's controls as the thing that holds the line.

## What the Compose Examples Do Not Prove

Local Compose and self-signed profiles demonstrate wiring, not production
security. Before you rely on any stage, be explicit that these are **out of
scope** for the local examples and must come from your platform:

- TLS termination with real certificates (Hangar expects a reverse proxy or
  load balancer in front -- nginx, Caddy, or Envoy).
- A WAF or edge rate control for public exposure.
- A real identity provider issuing signed JWTs. Hangar validates tokens; it
  does not mint them.
- Secret management. Configs reference secrets by environment interpolation
  (`${VAR}`); they never store the literal value.

## Stage 1: Local Development

The goal here is fast iteration, not safety. Run Hangar in the default topology
mode with auth disabled so there is nothing between you and your tools.

```bash
# stdio for a desktop client, or HTTP to poke it with curl
mcp-hangar --config ./config.yaml serve --http --host 127.0.0.1 --port 8000
```

What is true at this stage:

- Topology mode is the default `egress`: Hangar assumes trusted callers and
  exposes the full `hangar_*` meta-API.
- Auth is off. Bind to `127.0.0.1` so nothing off-box can reach it.
- The event store can run in memory -- volatile history is acceptable while you
  iterate.

The global `--config` also works after `serve` (both
`mcp-hangar --config X serve` and `mcp-hangar serve --config X` are accepted),
so you can standardize on one form across your scripts.

The companion recipe for this stage and the next is the **local and staging
profile cookbook** (docs issue #18).

## Stage 2: Staging

Staging is production's dress rehearsal. Same controls, non-production data.
This is where you turn auth **on** and make durability real.

What changes from Stage 1:

- Turn authentication on and stop allowing anonymous callers
  (`auth.enabled: true`, `auth.allow_anonymous: false`). Issue internal API
  keys per service principal. See
  [Cookbook 12 -- Auth & RBAC](../cookbook/12-auth-rbac.md).
- Make the event store durable. Set `event_store.driver: sqlite` on a writable
  volume, and leave `event_store.allow_memory_fallback: false` so a
  non-writable path **fails fast** at startup instead of silently dropping the
  audit trail. When the fallback is taken, `/health/ready` reports 503.
- Gate rollout on readiness. Point your orchestrator at `/health/live`
  (is the process up) and `/health/ready` (is it actually serving), and hold
  traffic until ready is green.
- Enable discovery only if you rely on it, and pin its scope. Under
  `discovery`, list explicit `sources` (for example a `docker` source) rather
  than discovering everything on the host. See
  [Cookbook 10 -- Discovery: Docker](../cookbook/10-discovery-docker.md).

Emit structured logs from staging onward so your log pipeline sees the same
shape it will see in production:

```bash
export MCP_JSON_LOGS=true
export MCP_LOG_LEVEL=INFO
```

## Stage 3: Production Read-Only and Controlled-Write

Now the boundary tightens. Most tools should be observable and callable but
**not** able to mutate host state; a small, audited set may write.

What changes from Stage 2:

- Sandbox container-mode MCP servers. Run them `read_only: true` (the default
  for container specs) and grant persistence only through explicit writable
  `volumes` mounts, for example `- "/absolute/path/to/data:/data:rw"`. Nothing
  outside a declared volume survives a restart, and nothing writes the root
  filesystem. See [Cookbook 04 -- Failover](../cookbook/04-failover.md) and the
  [Containers guide](CONTAINERS.md) for the container-mode caveats.
- Curate the tool surface with RBAC and per-target tool-access policy so each
  principal sees least-privilege. Controlled-write tools get their own role.
- Put rate limiting in front of your backends. Configure `rate_limit.rps` /
  `rate_limit.burst` in config (these take precedence over the
  `MCP_RATE_LIMIT_RPS` / `MCP_RATE_LIMIT_BURST` env vars). See
  [Cookbook 06 -- Rate Limiting](../cookbook/06-rate-limiting.md).
- Turn on tracing and metrics. OpenTelemetry tracing is on by default and is
  controlled by `MCP_TRACING_ENABLED`; scrape the Prometheus `/metrics`
  endpoint. See the [Observability guide](OBSERVABILITY.md) and
  [Cookbook 07 -- Observability: Metrics](../cookbook/07-observability-metrics.md).
- Keep a rollback path: run behind a reverse proxy, pin images to a digest (not
  `latest`), and keep the previous config so a bad rollout is one revert away.

The companion recipe for this stage is the **production read-only and
controlled-write cookbook** (docs issue #19).

## Stage 4: External Multi-Tenant Front Door

The final stage flips the trust model. Hangar now faces untrusted external
agents, so unauthenticated requests must be denied -- not proxied -- and each
tenant sees only the tools you allow.

What changes from Stage 3:

- Switch the topology mode: set `tool_access.mode: front_door`. In this mode a
  caller with no tenant identity is denied every tool (fail-closed), and
  external agents see flat per-tenant backend tool names instead of the
  `hangar_*` meta-API.
- Front the gateway with a real OIDC issuer. Hangar validates the JWTs and maps
  a tenant claim onto the caller identity; per-tenant `tool_access` and tool
  projection then govern what each tenant can call. See the
  [Front-Door guide](FRONT_DOOR.md) and
  [Cookbook 16 -- Front-Door Multi-Tenant](../cookbook/16-front-door-multi-tenant.md).
- Everything from Stage 3 still applies -- read-only sandboxes, RBAC, rate
  limits, tracing, durable event store, readiness gating -- plus the
  edge concerns (TLS, WAF, identity) listed under
  [What the Compose Examples Do Not Prove](#what-the-compose-examples-do-not-prove).

The companion recipe for this stage is the **external multi-tenant OIDC
front-door cookbook** (docs issue #20).

## Try It

Verify the two guarantees that most often regress between stages: readiness
gating and the fail-closed front door.

1. Confirm the readiness contract while the process is live.

   ```bash
   curl -s -o /dev/null -w "live=%{http_code}\n" http://localhost:8000/health/live
   curl -s -o /dev/null -w "ready=%{http_code}\n" http://localhost:8000/health/ready
   ```

   Expected output once the server is serving:

   ```text
   live=200
   ready=200
   ```

   If `ready` returns 503 while `live` is 200, the process is up but not
   serving -- for example a durable event store whose path is not writable.
   Hold traffic until ready is green.

2. Confirm a front-door gateway denies an unauthenticated call.

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
   ```

   Expected output when `tool_access.mode: front_door` and
   `auth.allow_anonymous: false`:

   ```text
   401
   ```

## What Just Happened

You did not deploy four different systems -- you deployed one system with four
progressively stricter postures. Each stage changed a small, named set of
controls:

- **Auth** went from off (dev) to on (staging onward) to OIDC per-tenant
  (front door).
- **Topology** went from the default `egress` (trusted callers, full meta-API)
  to `front_door` (untrusted agents, fail-closed, flat per-tenant tools).
- **Durability** went from in-memory to a `sqlite` event store that fails fast
  rather than silently losing the audit trail.
- **Health gating** used `/health/live` and `/health/ready` so rollouts wait
  for real readiness.
- **Guardrails** -- read-only container sandboxes with explicit writable
  volumes, rate limits, tracing, and `/metrics` -- accumulated as you moved up.

Because the controls are named and additive, a promotion is a diff you can
review, and a rollback is a diff you can revert.

## Promotion Checklist

Walk this before each promotion. The full pre-launch list lives in
[Cookbook 13 -- Production Checklist](../cookbook/13-production-checklist.md).

- [ ] Auth on for every stage above dev (`auth.enabled: true`,
      `auth.allow_anonymous: false`).
- [ ] Per-principal API keys or OIDC issuer configured; RBAC roles are
      least-privilege.
- [ ] Topology mode matches the trust boundary (`egress` internal,
      `front_door` external).
- [ ] Event store durable (`event_store.driver: sqlite`) on a writable volume;
      `allow_memory_fallback: false`.
- [ ] Container MCP servers run `read_only: true`; persistence only via
      explicit writable `volumes`.
- [ ] Rate limiting set (`rate_limit.rps` / `rate_limit.burst`, or the
      `MCP_RATE_LIMIT_RPS` / `MCP_RATE_LIMIT_BURST` env vars).
- [ ] Tracing and metrics wired (`MCP_TRACING_ENABLED`, Prometheus scraping
      `/metrics`).
- [ ] Structured logging on (`MCP_JSON_LOGS=true`, `MCP_LOG_LEVEL=INFO`).
- [ ] Orchestrator gates on `/health/live` and `/health/ready`.
- [ ] Discovery scope pinned to explicit `sources` (no host-wide discovery).
- [ ] Reverse proxy with real TLS in front; images pinned to a digest, not
      `latest`.
- [ ] Rollback rehearsed: previous config and image kept, one revert away.

## Companion Recipes

This umbrella guide references the following per-stage cookbooks. Where a
dedicated recipe is still forthcoming, the nearest published guide is linked
inline above.

- Local and staging profile cookbook -- docs issue #18.
- Production read-only and controlled-write cookbook -- docs issue #19.
- External multi-tenant OIDC front-door cookbook -- docs issue #20.

Published references used at each stage today:

- [Front-Door Mode & Per-Tenant Tool Governance](FRONT_DOOR.md)
- [Authentication & RBAC](AUTHENTICATION.md)
- [Observability](OBSERVABILITY.md)
- [Containers](CONTAINERS.md)
- [Cookbook 13 -- Production Checklist](../cookbook/13-production-checklist.md)
