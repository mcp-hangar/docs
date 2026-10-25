# Authentication Security Audit

Last audit date: 2026-04-23 (phase 6 security hardening refresh). Re-checked
against core 2.24.0 on 2026-10-04: the module-boundary, event-name, test-path and
replay-evidence sections below were corrected to what that release does. The
findings tables and open items were re-checked against core 2.34.2 on
2026-10-25; the verification evidence below is still the 2.24.0 replay.

## Scope

This audit covers the authentication, authorization, and request-enforcement paths in MCP Hangar after the phase 6 security hardening work:

- API key and JWT/OIDC authentication
- Role-based access control (RBAC) and `policy:write` authorization
- Tool access policies (TAP)
- HTTP and WebSocket auth enforcement
- Browser-oriented CSRF defense-in-depth on session suspension
- Core package loading between `src/` and `src/mcp_hangar/`

## Current Security Posture

### Authentication

- API requests rely on `request.state.auth`; WebSocket / generic ASGI paths use `scope["auth"]`.
- HTTP and WebSocket auth enforcement now share one core implementation in `src/mcp_hangar/server/api/middleware.py`.
- WebSocket connections support `?token=` bearer mapping for clients that cannot set custom headers.
- Trusted proxy resolution is centralized through `TrustedProxyResolver`, preventing spoofed `X-Forwarded-For` from untrusted peers.

### Authorization

- `/api/mcp_servers/{id}/l7_policy` (L7 egress policy push) no longer trusts a magic internal header.
- Policy push now requires an authenticated principal plus `policy:write` authorization.
- A refused policy push is recorded as an `AuthorizationDenied` event (an unauthenticated one is answered `401` before authorization runs). The `PolicyPushRejected` event type is still defined, but no code path emits it in 2.24.0.
- The `agent` role was retired along with the (now-discontinued) cluster agent product; `policy:write` remains a valid permission and is granted by the built-in `admin`, `provider-admin` and (since 2.28.0) `kubernetes-operator` roles.

### Browser CSRF Defense

- CSRF enforcement is intentionally scoped to browser-style session suspension requests.
- `POST /sessions/{session_id}/suspend` requires `X-Requested-With` only when the request looks browser-originated (`Origin`, `Referer`, or `Cookie` present).
- API key clients, bearer-token clients, and non-browser API callers bypass the CSRF check.
- This keeps REST API automation compatible while still defending against browser-triggered session suspension.

### WebSocket Security

- Authentication failures close the socket with code `1008` before `websocket.accept()`, so the client sees the handshake refused (uvicorn answers it as HTTP `403`) and the connection is never used.
- `Origin` validation happens before `websocket.accept()` to mitigate cross-site WebSocket hijacking.
- The WebSocket endpoints need a WebSocket library in the environment. Since 2.25.0 `websockets` is a dependency of `mcp-hangar`. Before that only the container image installed it, and on a `pip`/`uv` install of 2.24.0 or earlier the upgrade is never served -- the request is answered as plain HTTP (`401` without credentials) ([mcp-hangar/mcp-hangar#1676](https://github.com/mcp-hangar/mcp-hangar/issues/1676)).
- Per-connection backpressure is enforced with bounded queues.

### Module Boundary (optional auth and approvals components)

There is no paid tier or license split: MCP Hangar ships as a single MIT-licensed
package. The former `enterprise` module name was dropped from the codebase; auth
and approvals are in-core packages (`mcp_hangar.auth`, `mcp_hangar.approvals`).

- Core bootstrap/router code does not import those packages directly across server modules.
- They are loaded through one loader, `src/mcp_hangar/server/bootstrap/components.py`, which bootstraps them when configured and available and substitutes fallback components when they are not.
- The earlier entry-point discovery and monorepo fallback loader are retired: the separate optional package they discovered no longer exists, so the built-in modules are loaded directly.

## Findings Status

| Finding | Status | Notes |
| -------- | -------- | ------- |
| K-1 L7 policy push auth bypass | Fixed | `/api/mcp_servers/{id}/l7_policy` requires authenticated principal + `policy:write`; rejection events emitted |
| K-2 WebSocket auth / CSWSH gaps | Fixed | Shared auth enforcement, pre-accept Origin validation, bounded queue backpressure |
| K-3 Unsafe unauthenticated HTTP exposure | Fixed | Non-loopback HTTP bind blocked without auth unless explicitly overridden |
| K-4 CORS / host / CSRF hardening | Fixed | Explicit CORS config, TrustedHostMiddleware, browser-scoped CSRF defense |
| W-1/W-2 Header identity spoofing via proxies | Fixed | Trusted proxy resolution centralized and required for forwarded identity trust |
| W-3 SSRF on remote endpoints | Fixed (scoped) | SSRF validation blocks private/link-local targets for servers registered at runtime (REST API or discovery), and re-checks at connect time. Not covered: a `remote` server declared in `config.yaml`, which never reaches the registration handler (before 2.5.1 the connect-time re-check was also lost after a restart and on a follower replica; 2.5.1 carries it on the stored record). See [cookbook 23](../cookbook/23-harden-public-gateway.md#threat-model) |
| W-4 Unbounded suspended-session cache | Fixed | TTL-bounded cache with max size |
| W-5 JWT algorithm confusion | Fixed | Mixed symmetric/asymmetric algorithm families rejected |
| A-5 Core importing enterprise directly | Fixed | Server bootstrap/router path loads auth and approvals through one loader (`server/bootstrap/components.py`) |
| A-7 Divergent HTTP/WS auth middleware | Fixed | Core shared auth middleware path now handles both |

## Recommendations

| Item | Status | Notes |
| ------ | -------- | ------- |
| API key hash-only storage | Pass | Raw keys are not persisted |
| JWT algorithm-family validation | Pass | The OIDC/JWKS validator accepts only `RS256` and `ES256`; `HS256` is accepted only by the static-secret validator, so families never mix |
| Trusted proxy validation | Pass | Only configured proxies may influence forwarded source identity |
| WebSocket origin validation | Pass | Performed before accept |
| Shared auth logic across protocols | Pass | One core implementation reduces drift |
| Core/optional-component import boundary | Pass | Centralized in `server/bootstrap/components.py` |
| Repo-wide Ruff cleanliness | Pass | `uv run ruff check src/ tests/` reports no findings at 2.24.0 |
| Manual exploit verification | Pass | Replay on 2.24.0 confirmed K-1 returns 401, K-2 refuses the unauthenticated or wrong-`Origin` handshake (403), K-3 exits 1 on a non-loopback no-auth start, and K-4 rejects a hostile `Host` (400 on `/api`, 421 on `/mcp`) |
| TLS / mTLS at deployment edge | Manual | Must be enforced by deployment topology / reverse proxy |

## Verification Evidence

Re-run against core 2.24.0 on 2026-10-04:

- `uv run ruff check src/ tests/` and `uv run mypy src/` -- pass
- Manual exploit replay of K-1..K-4 on a live gateway -- pass: `/api/mcp_servers/{id}/l7_policy` without credentials returns 401 and with a `developer` key 403; an unauthenticated WebSocket, or one from an unlisted `Origin`, is refused at the handshake (403); a no-auth start on the default `0.0.0.0` exits 1 with `http_auth_required_for_non_loopback`; a hostile `Host` is rejected with 400 on `/api` and 421 on `/mcp`
- Focused security and boundary suites (52 tests, pass):
  - `tests/unit/test_security_critical_paths.py`
  - `tests/unit/test_security_identity_and_network.py`
  - `tests/unit/test_bootstrap_components_boundary.py`
  - `tests/unit/test_bootstrap_components_loading.py`
  - `tests/unit/test_api_auth_enforcement.py`
  - `tests/unit/test_ws_auth.py`

## Open Items

Open defects in this audit's scope, as of 2.34.2:

- `POST /api/auth/roles/assign` with a role name that does not exist, or a scope other than `global` or `tenant:<id>`, answers `500` rather than a `4xx`. Nothing is assigned. Not filed as an issue yet.
- A declared `auth.stdio.principal` has its `roles` enforced only on a front door or with auth on. With auth off in `egress` mode every `hangar_*` management tool is allowed to it, whatever its roles; since 2.34.2 boot says so with `stdio_principal_roles_not_enforced`. Whether egress mode should enforce them is an open design question ([mcp-hangar/mcp-hangar#2079](https://github.com/mcp-hangar/mcp-hangar/issues/2079)).

Fixed in 2.34.2. A gateway older than that still has them:

- A line removed from `auth.role_assignments` left its grant in force on a durable auth store. Each boot with auth on now revokes the grants the file applied and no longer lists; grants made through the API or `bootstrap-admin` are never revoked, and a grant from before 2.34.2 that the file does not list is kept and logged as `untracked_role_assignment_not_in_config` ([mcp-hangar/mcp-hangar#2052](https://github.com/mcp-hangar/mcp-hangar/issues/2052)).
- With two or more trusted OIDC issuers, each could sign a token naming any tenant. `allowed_tenants` on an issuer entry now binds it, and boot warns with `oidc_issuers_not_bound_to_tenants` while any issuer is unbound. A `global` role grant to a subject or group is still shared across issuers ([mcp-hangar/mcp-hangar#2044](https://github.com/mcp-hangar/mcp-hangar/issues/2044)).
- An OPA allow overrides an RBAC deny with no tenant scope; that default is unchanged and now logged as `opa_may_widen_rbac`, and `auth.opa.require_both: true` makes both decisions necessary ([mcp-hangar/mcp-hangar#2081](https://github.com/mcp-hangar/mcp-hangar/issues/2081)).
- A `developer` could register a `subprocess` or container server over REST, which runs a command of its choice on the gateway host. That now needs `mcp_servers:local_launch`, held by `admin` and `provider-admin` only ([mcp-hangar/mcp-hangar#2025](https://github.com/mcp-hangar/mcp-hangar/issues/2025)).
- A key created with an `expires_at` without a UTC offset failed every authentication with a `500`; it is now read as UTC, and an unparseable value is refused with `422` ([mcp-hangar/mcp-hangar#2046](https://github.com/mcp-hangar/mcp-hangar/issues/2046)).
- `Authorization: bearer <jwt>` (any spelling but `Bearer`) counted as no credential; the scheme is now matched case-insensitively ([mcp-hangar/mcp-hangar#2060](https://github.com/mcp-hangar/mcp-hangar/issues/2060)).

Fixed in 2.29.0. A gateway older than that still has them:

- `/config/diff` and `/config/backup` accepted a `config_path` and ignored `--config`; both now act on the file the gateway was started with and answer `422` to `config_path` ([mcp-hangar/mcp-hangar#1652](https://github.com/mcp-hangar/mcp-hangar/issues/1652)).
- `oidc.clock_skew_leeway_seconds` was never parsed, so the leeway was always 60 seconds. It now applies, and a value that is not a whole number from 0 to 300 refuses the configuration ([mcp-hangar/mcp-hangar#1654](https://github.com/mcp-hangar/mcp-hangar/issues/1654)).
- A global `developer` could withdraw or restore a tool for all tenants. Doing so without a `tenant_id` now needs `admin:*` ([mcp-hangar/mcp-hangar#1656](https://github.com/mcp-hangar/mcp-hangar/issues/1656)).
- A bare `mcp-hangar` ignored `MCP_HTTP_HOST` / `MCP_HTTP_PORT` ([mcp-hangar/mcp-hangar#1651](https://github.com/mcp-hangar/mcp-hangar/issues/1651)); `python -m mcp_hangar.server` read them the same way from 2.31.0.

Fixed in 2.25.0. A gateway older than that still has them:

- An explicit `--config` / `MCP_CONFIG` path that does not exist booted a demo configuration; it now stops the gateway ([mcp-hangar/mcp-hangar#1650](https://github.com/mcp-hangar/mcp-hangar/issues/1650)).

- A `tools:` access policy with one invalid field was dropped whole with only a warning, so the gateway enforced no policy for that server -- denied and approval-listed tools ran ([mcp-hangar/mcp-hangar#1648](https://github.com/mcp-hangar/mcp-hangar/issues/1648)); and a policy list written as a string was split into its characters, so `deny_list: add` allowed `add` ([mcp-hangar/mcp-hangar#1718](https://github.com/mcp-hangar/mcp-hangar/issues/1718)). Since 2.25.0 either refuses the boot, and a reload, naming the scope and the field.
- The auth routes took `assigned_by` / `created_by` / `revoked_by` / `updated_by` from the request body, so the actor recorded for a key or role change was caller-supplied ([mcp-hangar/mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)). Since 2.25.0 the actor is the authenticated principal (`anonymous` with auth off), and a body carrying one of those fields is refused with `422`. An auth event written by an older gateway names whoever its request body said.
