# 23 -- Harden a Public Authenticated MCP Gateway

> **Prerequisite:** [22 -- External Multi-Tenant OIDC](22-external-multitenant-oidc.md)
> **You will need:** A working front-door deployment (recipe 22), plus platform ownership of your public edge (managed LB/WAF, DNS, certificates)
> **Time:** Read first, then plan -- this is a reference architecture, not a 20-minute run
> **Adds:** The trust boundary, control catalog, threat model, launch checklist, rollback plan, and incident-response handoff for exposing a Hangar front door to the public internet

## The Problem

Recipe 22 proved the *identity* guarantees of a front door on your laptop: two
tenants authenticate through OIDC and each sees only its own tools. That recipe
is deliberately a local, test-only profile. Exposing the same gateway to
untrusted traffic on the public internet needs a different class of guarantee --
a hardened network boundary, edge protection, durable and immutable audit,
high availability, and a rehearsed incident path.

This recipe is a **reference architecture and checklist**, not a copy-paste
deploy guide. Every config block below is **illustrative and uses
placeholders**. The runtime controls Hangar owns are named against real
config keys and environment variables; the edge controls it does *not* own are
called out as your platform's responsibility.

> **Managed, publicly trusted TLS only.** The self-signed certificates and local
> Keycloak in recipe 22 are an **integration-test convenience only**. A public
> gateway MUST terminate TLS with a managed or publicly trusted certificate at a
> load balancer, WAF, or reverse proxy you operate. Never expose a self-signed
> or locally minted certificate to the internet.
>
> **Security review gate.** Any *concrete* public-edge configuration -- real
> domains, host allow-lists, CORS origins, header rules, certificates, secrets,
> and upstream rate limits -- MUST pass human security review before it is
> published or deployed. Nothing in this recipe is a substitute for that review.

## The Trust Boundary

There are two networks and one boundary. Public traffic terminates at an edge
you operate; Hangar and its providers run on a private network with **no
directly reachable service ports**.

```text
                    PUBLIC INTERNET (untrusted)
                              |
                    TLS (managed / publicly trusted cert)
                              |
        +---------------------v----------------------+
        |   EDGE  (external-infrastructure)          |
        |   managed LB / WAF / DDoS / edge rate cap  |
        |   terminates TLS, routes by host           |
        +---------------------+----------------------+
                              |  private network only
  ====== PRIVATE SERVICE NETWORK (no public ingress) ======
                              |
              +---------------v---------------+
              |   Hangar front door (HA)      |   tool_access.mode: front_door
              |   OIDC validation, RBAC,      |   auth.allow_anonymous: false
              |   per-tenant projection,      |   MCP_TRUSTED_HOSTS / CORS scoped
              |   rate limiting, audit        |
              +---+-------------------+-------+
                  |                   |
        per-provider service    durable stores
        accounts (least priv)   (auth + event/audit)
                  |                   |
        +---------v------+   +--------v---------+
        |  MCP providers |   |  auth store +    |
        |  (private)     |   |  event store     |
        +----------------+   +------------------+
```

The single load-bearing idea, carried over from the
[Deployment Playbook](../guides/DEPLOYMENT_PLAYBOOK.md): **the topology mode and
auth posture are the boundary, not the network.** The private network is
defense in depth. The thing that actually holds the line is
`tool_access.mode: front_door` with `auth.allow_anonymous: false`, which denies
an unauthenticated caller before any backend is consulted (recipe 22, step 3).

### Verify the boundary

The boundary is only real if you can prove it. Two checks:

1. **No direct service port from the public side.** From an external host (not
   on the private network), a direct hit on Hangar's service port must not
   connect. Only the edge's TLS port answers.

   ```bash
   # From outside the private network: the service port is unreachable.
   nc -z -w3 hangar.internal.example 8000 ; echo "exit=$?"   # non-zero = refused/filtered
   # Only the public edge answers, and only over TLS.
   curl -sS -o /dev/null -w "%{http_code}\n" https://gateway.example/health/live
   ```

2. **Anonymous traffic is denied at the door, not proxied.** Through the edge,
   an unauthenticated MCP call fails closed:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://gateway.example/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'   # -> 401
   ```

   `gateway.example`, `hangar.internal.example`, and the port are placeholders.
   Substitute your reviewed values.

## Control Catalog (who owns each control)

Every control is classified by **who is responsible** for it:

- **application** -- a Hangar config key or environment variable you set.
- **provider** -- a property of a backend MCP server or the identity provider.
- **external-infrastructure** -- your platform: LB/WAF, DNS, managed database,
  SIEM, orchestrator.

| Control | Responsibility | How it is delivered |
| --- | --- | --- |
| Trusted TLS at the edge | external-infrastructure | Managed/publicly trusted cert on the LB/WAF; Hangar expects TLS terminated upstream and speaks plain HTTP on the private net |
| Backend (provider) TLS verification | application + provider | `mcp_servers.<id>.tls.verify_ssl: true` for `remote` providers -- the field is `verify_ssl`, and it is on by default; never disable it in production. `tls.ca_cert_path` points at your own CA. Both were accepted and silently discarded before 2.5.0, which failed closed for the first and made an upstream behind a private CA unreachable for the second |
| Host boundary | application + external-infrastructure | `MCP_TRUSTED_HOSTS` (Hangar rejects off-allow-list `Host` headers; dev default `localhost,127.0.0.1,::1,testserver` MUST be replaced) + host-based routing at the edge |
| Real client IP behind the proxy | application | `MCP_TRUSTED_PROXIES` so source IP is resolved from the proxy chain, not spoofable headers |
| CORS scope | application | `MCP_CORS_ORIGINS` (dev default `http://localhost:5173` MUST be replaced with your reviewed origins); `MCP_CORS_CREDENTIALS` only if you truly need credentialed cross-origin calls |
| OIDC signing-key rotation | provider + application | IdP rotates its JWKS; Hangar's JWKS client re-fetches signing keys on an unknown `kid`, so rotation needs no Hangar restart. Hangar warns (`jwks_uri_not_https`) if the JWKS URI is not HTTPS |
| Token lifetime ceiling | application | `MCP_JWT_MAX_TOKEN_LIFETIME` caps accepted `exp - iat` (default 3600s) independent of what the IdP mints |
| Rate-limiting scope | application + external-infrastructure | `rate_limit.rps` / `rate_limit.burst` (or `MCP_RATE_LIMIT_RPS` / `MCP_RATE_LIMIT_BURST`) inside Hangar, *plus* an edge/WAF rate cap and DDoS protection you own |
| Durable storage | application + external-infrastructure | *Since 2.5.0:* one decision -- `persistence.backend: sqlite` on a durable, backed-up volume, or `postgresql`. A backend now serves **every** persisted concern or is refused, so the 2.4.0 trap of selecting PostgreSQL and silently losing tool-access policy management is unrepresentable. On 2.4.0 and earlier, use `auth.storage.driver: sqlite`: the PostgreSQL driver there does not carry tool-access policies, and needs `psycopg2-binary` installed explicitly |
| Durable audit / event storage | application + external-infrastructure | *Since 2.5.0:* covered by the `persistence.backend` above -- the log and its delivery mark come from the selected backend, which is durable as a whole, so there is no fallback to opt out of. On 2.4.0 and earlier: `event_store.driver: sqlite` with `allow_memory_fallback: false` on a writable, backed-up volume; readiness turns `503` if durability is lost |
| Central immutable log / SIEM ingest | application + external-infrastructure | Structured JSON logs (`MCP_JSON_LOGS=true`, `MCP_LOG_LEVEL=INFO`) shipped to an append-only, access-controlled SIEM your platform owns |
| High availability | application + external-infrastructure | *Since 2.5.0:* supported, with conditions. Requires `persistence.backend: postgresql` shared by every replica, a `coordination:` block, and `remote`-mode servers -- `subprocess` and `docker` run a child process of one gateway and are refused in a coordinated deployment. Exactly one replica manages the fleet at a time; all of them serve. Known costs: rate limits are counted **per instance** (three replicas admit three times the configured rate -- put a fleet-wide cap at the ingress), anything travelling by the shared log lags by a poll interval, and a leader that dies without releasing its lease leaves the fleet unmanaged -- though still served -- until the tenure expires. See [Running more than one replica](25-multiple-replicas.md) and [ADR-020](../adr/ADR-020-high-availability.md). **On 2.4.0 and earlier, run a single instance**: replicas there are not safe, and the failure is silent |
| Per-provider service accounts | application + provider | Each `remote` provider carries its own least-privilege credential (`mcp_servers.<id>.auth`), scoped at the backend; no shared super-credential |

## Illustrative Config (placeholders -- review before use)

This shows only the *shape* of the production knobs on top of the recipe-22
front door. It is not deployable as written.

```yaml
# config.yaml -- ILLUSTRATIVE. Every value is a placeholder pending security review.

tool_access:
  mode: front_door                 # untrusted edge: fail-closed, flat per-tenant tools

auth:
  enabled: true
  allow_anonymous: false           # deny unauthenticated callers before any backend
  oidc:
    enabled: true
    issuer: https://idp.example/realms/prod          # your production IdP
    jwks_uri: https://idp.example/realms/prod/protocol/openid-connect/certs  # HTTPS
    resource_uri: https://gateway.example            # advertised AND enforced as aud
    tenant_claim: tenant_id

  # Storage is chosen once, below, for every persisted concern. On 2.4.0 and
  # earlier it was picked here instead -- `storage: {driver: sqlite, path: ...}`
  # -- independently of the event store, which is how a deployment could end up
  # half on PostgreSQL.

# Durable storage -- one decision (since 2.5.0). A backend serves every
# persisted concern or it is refused, so the half-configured deployment is
# unrepresentable. `sqlite` is the single-node answer; `postgresql` is the only
# one several replicas can share.
persistence:
  backend: sqlite                  # sqlite | postgresql
  sqlite:
    data_dir: /app/data            # writable, backed-up volume
  # postgresql:
  #   host: db.internal.example    # managed, private, backed up
  #   database: mcp_hangar
  #   user: hangar
  #   password: ${HANGAR_DB_PASSWORD}

# No `event_store:` block: with a backend selected, the log and its delivery
# mark come from it, and a durability negotiation would have nothing to decide
# -- a backend is durable as a whole. On 2.4.0 and earlier this is where the
# audit trail was configured, and `allow_memory_fallback: false` mattered:
#
#   event_store:
#     enabled: true
#     driver: sqlite
#     path: /app/data/events.db
#     allow_memory_fallback: false

# In-process rate limit. This is NOT your DDoS defense -- the edge WAF is.
rate_limit:
  rps: 50                          # placeholder; size against real capacity
  burst: 100

mcp_servers:
  reports:
    mode: remote
    endpoint: https://reports.internal.example/mcp
    tls:
      verify_ssl: true             # never disable backend TLS verification
      # ca_cert_path: /etc/ssl/internal-ca.pem   # for an upstream behind your own CA
    auth:
      type: bearer
      token: ${REPORTS_PROVIDER_TOKEN}   # per-provider service account, least privilege

    tool_access:                   # tenant-scoped, read-only surface
      member:
        "tenant:acme":
          allow_list: [list_reports, get_report]   # read-only tools only
```

The public-edge pieces -- the LB/WAF, the TLS certificate, host routing, edge
rate caps, DDoS rules, and the SIEM pipeline -- are intentionally **absent**
here. They are external-infrastructure, and their concrete configuration is
exactly what security review must approve before publication.

## PostgreSQL Connection Pooling

*Applies when `persistence.backend: postgresql`.* Ownership:
**external-infrastructure** (the pooler and the database), with an application
note.

Hangar talks to PostgreSQL through an in-process connection pool. That pool
returns a connection to the pool only after rolling back whatever transaction
was on it, and the auth store's read paths (`get_role`,
`get_roles_for_principal`, `list_keys`, `count_keys`, and the key-lookup miss)
commit the transaction their `SELECT` opened before yielding the connection
back. So a single Hangar process does not hand back a connection that is *idle
in transaction*.

That guarantee is about the *in-process* pool. If you additionally place an
external connection pooler -- **pgbouncer** is the common one -- between Hangar
and PostgreSQL, its **pooling mode** matters:

- **Session pooling** (recommended) assigns a server connection to a client for
  the life of the client connection. This matches how Hangar's own pool holds
  connections, and a transaction that is briefly left open blocks nothing but
  that one already-dedicated server connection.
- **Transaction pooling** returns the server connection to pgbouncer's pool
  only at the *end of each transaction* (`COMMIT`/`ROLLBACK`). A connection that
  is handed back to Hangar's in-process pool mid-transaction -- or any future
  read path added without closing its transaction -- would be seen by pgbouncer
  as still in a transaction, so pgbouncer cannot reclaim that server connection.

Under transaction pooling, a stray open read transaction is not merely untidy:

1. **pgbouncer server-connection pinning and exhaustion.** Each un-closed
   transaction pins one of pgbouncer's finite server connections. Enough of them
   and the pool has nothing left to lend, and *new authentication requests
   cannot obtain a backend connection* -- an auth-path outage at exactly the
   layer this guide is hardening.
2. **VACUUM bloat.** An open transaction -- even a read-only one -- holds a
   snapshot, which holds back the `xmin` horizon that `VACUUM` may reclaim below.
   Dead tuples in the auth tables accumulate and the tables bloat until the
   transaction ends.

So, if you deploy behind pgbouncer in transaction-pooling mode, add a
database-side backstop that force-closes any transaction left idle:

```sql
-- On the database or the Hangar role: cap how long a session may sit
-- "idle in transaction" before the server aborts it and frees the connection.
ALTER ROLE hangar SET idle_in_transaction_session_timeout = '30s';
```

Prefer **session pooling** if you have the connection budget for it -- it sizes
against Hangar's own pool (`persistence.postgresql` `min_connections` /
`max_connections`) and removes the failure mode rather than bounding it.
`idle_in_transaction_session_timeout` is the belt-and-suspenders backstop when
transaction pooling is a hard requirement.

## Try It: Tenant-Scoped Read-Only Provider + Global Withdrawal

You can rehearse the two guarantees that matter most at the edge against your
recipe-22 stack (local, test-only TLS). The commands are the same over the
public edge; only the host and scheme change to your reviewed HTTPS endpoint.

1. Confirm a tenant sees only its read-only surface. With the `reports`
   provider's `allow_list` of `list_reports`, `get_report` for `tenant:acme`:

   ```bash
   curl -s https://gateway.example/mcp \
     -H "Authorization: Bearer $ACME_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' \
     | jq -S '.result.tools[].name'
   ```

   Expected -- a flat, read-only surface, no meta-API, no other tenant's tools:

   ```text
   "get_report"
   "list_reports"
   ```

2. Prove a tool the tenant may not call is refused even by name (the projection
   hides it *and* the call path re-checks it):

   ```bash
   curl -s https://gateway.example/mcp \
     -H "Authorization: Bearer $ACME_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"delete_report","arguments":{}},"id":1}' \
     | jq '.error.code // .result.isError'   # -> -32601 (method not found)
   ```

3. Withdraw a tool **globally** at runtime and verify it disappears for every
   tenant. This needs an admin key with the `lifecycle` action on `mcp_servers`:

   ```bash
   curl -s -X POST \
     https://gateway.example/api/admin/tools/reports/get_report/withdraw \
     -H "X-API-Key: <admin-key>" \
     -H "Content-Type: application/json" \
     -d '{}' | jq
   ```

   Expected -- a global withdrawal (no `tenant_id`):

   ```json
   {"withdrawn": true, "mcp_server": "reports", "tool": "get_report", "tenant_id": null}
   ```

   Re-run step 1: `get_report` is gone from acme's list, and a `tools/call`
   for it is refused at the enforcement path before any backend is contacted.
   `restore` with the same body reverses it. This is your emergency "pull a
   tool from the whole fleet" lever -- rehearse it before you need it.

## Threat Model

State what you are defending against, and what you are not.

| Threat | Primary control | Owner |
| --- | --- | --- |
| Unauthenticated access to tools | `tool_access.mode: front_door` + `auth.allow_anonymous: false` (fail-closed) | application |
| Forged / wrong-audience / unknown-issuer token | OIDC signature + `iss` + `aud` (`resource_uri`) validation; unknown issuer never reaches a signature check | application + provider |
| Long-lived or replayed token | `MCP_JWT_MAX_TOKEN_LIFETIME` ceiling; rotate keys at the IdP; short IdP token lifetimes | application + provider |
| Cross-tenant data access | Per-tenant projection + authoritative call-path check (recipe 22) | application |
| Host-header / CORS abuse | `MCP_TRUSTED_HOSTS`, scoped `MCP_CORS_ORIGINS`, `MCP_TRUSTED_PROXIES` | application |
| Volumetric / DDoS flooding | Edge WAF + DDoS + edge rate cap (Hangar's `rate_limit` is a backstop, not the defense) | external-infrastructure |
| Compromised backend provider | Least-privilege per-provider service account; sandboxed container providers (recipe 20); deny-by-default L7 egress policy ([`MCPEgressPolicy`](../guides/EGRESS_POLICY.md)) constraining which upstreams/tool calls/arguments a server may make | provider + application |
| Lost or tampered audit trail | Durable event log -- a selected `persistence.backend`, or `allow_memory_fallback: false` on 2.4.0 and earlier -- plus immutable SIEM ingest | application + external-infrastructure |
| TLS interception | Managed/publicly trusted edge cert; verified backend TLS (`tls.verify_ssl: true`, the default) | external-infrastructure + provider |
| SSRF / DNS rebinding to internal endpoints | A human-registered endpoint is refused if it resolves to any private range or the cloud metadata address; the check is re-applied **at connect time** against the IP actually dialed, and the connection is pinned to that validated IP (the original hostname is kept for the `Host` header and TLS verification), so a name that passed registration cannot be re-pointed at `169.254.169.254` / `10.x` / `127.0.0.1` on a later call. A discovery-sourced endpoint may be private, but only at an address the container runtime reported for it. | application |

**Backend SSRF / DNS rebinding.** The endpoint an operator registers for a
remote (HTTP) MCP server is validated for SSRF when it is registered *and* again
on every outbound connection: the guard re-resolves the hostname, refuses it if
it now resolves to a private range or the cloud metadata endpoint (for a
human-supplied endpoint), and connects to the exact IP it validated while
sending the original hostname as the `Host` header and TLS SNI. This closes DNS
rebinding, where a name that resolved to a public address at registration is
re-pointed at an internal one before the next tool call. A discovery-sourced
endpoint is allowed to be private, but only at the specific address the
container runtime reported for it -- provenance grants a *named address*, not a
whole private range.

**Out of scope / not claimed here:** Hangar is an OAuth *Resource Server*; it
validates tokens but never issues them -- IdP hardening is the provider's job.
For *egress*, Hangar now ships a built-in, deny-by-default L7 policy engine --
[`MCPEgressPolicy`](../guides/EGRESS_POLICY.md) -- that constrains which
upstreams a server may reach and which tool calls and arguments it may make, so
outbound tool invocation is no longer ungoverned (see the
[Egress Policy guide](../guides/EGRESS_POLICY.md) for its trust boundary and the
network backstop it depends on). What is still *not* claimed is a composed
*inbound* authorization gate from an external general-purpose policy engine: an
external engine (OPA) can be wired in as an *optional, future* layer, but the
runtime does not today enforce a composed "RBAC **and** OPA must both allow"
decision, so do not present OPA as a required second gate. Physical/host
security and the managed database's own hardening are external-infrastructure.

## Launch Checklist

Walk this before opening the gateway to the public. The general promotion list
lives in [Cookbook 13 -- Production Checklist](13-production-checklist.md); this
adds the public-edge items.

- [ ] **TLS:** managed/publicly trusted certificate at the edge; no self-signed
      cert exposed; backend `mcp_servers.<id>.tls.verify_ssl: true`.
- [ ] **Network boundary:** no public ingress to Hangar's service port; only the
      edge is reachable; the `nc`/`curl` boundary checks above pass.
- [ ] **WAF / DDoS:** edge WAF and DDoS protection enabled with an edge rate cap;
      Hangar `rate_limit.rps` / `rate_limit.burst` set as a backstop.
- [ ] **Identity:** `tool_access.mode: front_door`, `auth.allow_anonymous: false`,
      OIDC `issuer`/`jwks_uri` (HTTPS)/`resource_uri` set; anonymous call returns
      `401`; wrong-audience token rejected; `MCP_JWT_MAX_TOKEN_LIFETIME` set.
- [ ] **Host / CORS:** `MCP_TRUSTED_HOSTS` and `MCP_CORS_ORIGINS` replaced with
      reviewed production values (never the dev defaults); `MCP_TRUSTED_PROXIES`
      set to your proxy chain.
- [ ] **Storage:** *since 2.5.0* -- one `persistence.backend`: `sqlite` on a
      durable volume, or `postgresql` on a managed, backed-up database; backups
      verified restorable. On 2.4.0 and earlier: `auth.storage.driver: sqlite`
      plus a durable `event_store` with `allow_memory_fallback: false`.
- [ ] **Connection pooling:** if PostgreSQL is fronted by pgbouncer, use
      **session pooling**, or set `idle_in_transaction_session_timeout` on the
      Hangar role when transaction pooling is required (see
      [PostgreSQL Connection Pooling](#postgresql-connection-pooling)).
- [ ] **Logging / SIEM:** `MCP_JSON_LOGS=true`, `MCP_LOG_LEVEL=INFO`; logs shipped
      to an append-only, access-controlled SIEM.
- [ ] **HA:** *since 2.5.0* -- replicas require one shared
      `persistence.backend: postgresql`, a `coordination:` block, and
      `remote`-mode servers; **exactly one** pod reports `manages_fleet: true`
      at `GET /api/system`, asked pod by pod rather than through the Service;
      the fleet-wide request cap is at the ingress, because Hangar's own limit
      counts per instance. On 2.4.0 and earlier, run a **single** instance.
      Orchestrator gates on `/health/live` and `/health/ready`.
- [ ] **Per-provider service accounts:** each provider has its own least-privilege
      credential; no shared super-credential; tenant surfaces are least-privilege.
- [ ] **Incident readiness:** global tool-withdrawal rehearsed; rollback rehearsed;
      on-call and SIEM alerts wired.
- [ ] **Security review:** the concrete public-edge configuration is approved.

## Rollback Plan

A public rollout must be one reversible step, not a rebuild.

- **Pin, don't chase.** Deploy a pinned image digest (not `latest`) and keep the
  previous digest and the previous `config.yaml` one revert away.
- **Roll back at the edge first.** The fastest safe reaction to a bad rollout is
  to shift the LB back to the last-good replica set; the private network makes
  this a routing change, not a redeploy.
- **Withdraw before you roll.** If a single tool or provider is the problem, use
  the runtime global withdrawal (Try It, step 3) to pull it fleet-wide in
  seconds while you prepare the full rollback.
- **Health-gate the return.** Bring the previous version back behind
  `/health/ready`; hold traffic until readiness is green so a node that lost
  durable storage is never routed to.
- **Config reload, not restart, for scoped changes.** Tightening a tenant's
  `tool_access` or withdrawing a tool is a reload-driven overlay; you do not need
  to restart the fleet to narrow the blast radius.

## Incident-Response Handoff

When something is wrong at the edge, the responder needs a known path:

1. **Contain.** Withdraw the affected tool(s) globally (Try It, step 3) and/or
   shift the edge away from the affected replicas. Rotate the OIDC signing keys
   at the IdP and any leaked per-provider credential; Hangar re-fetches JWKS on
   the new `kid` without a restart.
2. **Preserve evidence.** Freeze and snapshot the durable event store and the
   SIEM window covering the incident *before* any redeploy overwrites state.
3. **Attribute.** Use the structured logs and metrics (below) to bound which
   tenants, providers, and tools were involved.
4. **Recover.** Roll back per the plan above; restore the affected provider's
   least-privilege credential.
5. **Review.** Feed findings back into the threat model and launch checklist.

Name the on-call owner, the SIEM query location, and the credential-rotation
runbook here for your deployment -- those are environment-specific and belong in
your internal runbook, not in this reference.

## Evidence Collection

Everything a responder or auditor needs is observable at the boundary:

- **HTTP responses** are first-line evidence: `401` for anonymous/wrong-audience
  calls, JSON-RPC `-32601` for a projection miss, and a `CallToolResult` with
  `isError: true` for a call denied at the enforcement path. No denied call
  reaches a backend.
- **Structured logs** (JSON) carry the wiring and per-request surface: OIDC
  enablement, per-tenant policy loads, and per-request `tenant_id` and tool
  counts. Shipped immutably to the SIEM, they are the durable audit record.
- **Metrics** at `/metrics` quantify the boundary over time:
  `mcp_hangar_tool_access_denied` (authorization refusals),
  `mcp_hangar_rate_limit_hits` (throttling pressure),
  `mcp_hangar_tool_calls_total` (call volume by outcome),
  `mcp_hangar_mcp_server_up` and `mcp_hangar_health_checks_total`
  (provider and gateway health). Alert on denials and rate-limit spikes as
  early indicators of probing.
- **The durable event store** is the tamper-evident trail of state changes
  (tool withdrawals/restores, key events). A selected `persistence.backend` is
  durable as a whole; under the pre-2.5.0 keys, `allow_memory_fallback: false`
  is what makes it either persist or pull the node from readiness.

## Key Config Reference

| Key / Var | Where | Description |
| --- | --- | --- |
| `tool_access.mode` | config | `front_door` for an untrusted public edge (fail-closed) |
| `auth.allow_anonymous` | config | Keep `false` at a public edge |
| `auth.oidc.resource_uri` | config | Public URI advertised as `resource` and enforced as `aud` |
| `persistence.backend` | config | *Since 2.5.0.* `sqlite` or `postgresql`, for every persisted concern at once; `postgresql` is required for more than one replica |
| `coordination` | config | *Since 2.5.0.* Declares that these replicas are one gateway. Refused on a backend they cannot share |
| `auth.storage.driver` | config | Pre-2.5.0 auth store: `memory`, `sqlite`, or `postgresql`. Contradicting a selected `persistence.backend` is refused at startup |
| `event_store.allow_memory_fallback` | config | Pre-2.5.0. Keep `false` so a non-durable audit store fails fast |
| `mcp_servers.<id>.tls.verify_ssl` | config | Verify backend TLS. On by default; never disable in production |
| `mcp_servers.<id>.tls.ca_cert_path` | config | Trust an upstream signed by your own CA |
| `mcp_servers.<id>.auth` | config | Per-provider service-account credential (least privilege) |
| `rate_limit.rps` / `rate_limit.burst` | config | In-process rate backstop (not DDoS defense) |
| `MCP_TRUSTED_HOSTS` | env | Allowed `Host` values (replace the dev default) |
| `MCP_TRUSTED_PROXIES` | env | Proxy chain used to resolve the real client IP |
| `MCP_CORS_ORIGINS` / `MCP_CORS_CREDENTIALS` | env | CORS allow-list (replace the dev default) / credentialed CORS |
| `MCP_JWT_MAX_TOKEN_LIFETIME` | env | Ceiling on accepted token `exp - iat` (default 3600s) |
| `MCP_RATE_LIMIT_RPS` / `MCP_RATE_LIMIT_BURST` | env | Rate-limit fallback when `rate_limit:` is omitted |
| `MCP_JSON_LOGS` / `MCP_LOG_LEVEL` | env | Structured logs for SIEM ingest |
| `MCP_TRACING_ENABLED` / `MCP_ENVIRONMENT` | env | Tracing to your collector; environment resource attribute |

## What's Next

This recipe is the public-edge capstone of the Deployment Playbook series
([mcp-hangar/docs#17](https://github.com/mcp-hangar/docs/issues/17)). To go
deeper on the pieces it assembles:

- Identity and per-tenant isolation end to end --
  [22 -- External Multi-Tenant OIDC](22-external-multitenant-oidc.md).
- Multiple IdPs, one per customer --
  [17 -- Multi-Issuer Front Door](17-multi-issuer-front-door.md).
- Sandboxed, read-only providers with controlled writes --
  [20 -- Read-Only Rootfs & Controlled Writes](20-readonly-controlled-write.md).
- The stage-by-stage maturity model --
  [Deployment Playbook](../guides/DEPLOYMENT_PLAYBOOK.md).
- Pre-launch fundamentals --
  [13 -- Production Checklist](13-production-checklist.md).

Before you publish any concrete public-edge configuration, route it through
security review. This document is the architecture and the checklist; the
approved, environment-specific edge config lives behind that review.
