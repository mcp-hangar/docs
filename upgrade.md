---
title: Upgrade Guide
---

This guide covers user-visible migration steps between MCP Hangar releases.

## Upgrade to 1.6.0

MCP Hangar 1.6.0 is an observability-hardening release: tool-invocation
telemetry now follows the OpenTelemetry GenAI/MCP semantic conventions, the
transport message metrics are wired, and it ships the L7 egress-policy
([`MCPEgressPolicy`](guides/EGRESS_POLICY.md)) enforcement plane end to end.
Upgrade is drop-in (`pip install -U mcp-hangar==1.6.0`, or pull
`ghcr.io/mcp-hangar/mcp-hangar:1.6.0`); the notes below cover what changed for
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
