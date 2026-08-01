---
title: Upgrade Guide
---

This guide covers user-visible migration steps between MCP Hangar releases.

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
  [configuration reference](reference/configuration) if you relied on the old
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
