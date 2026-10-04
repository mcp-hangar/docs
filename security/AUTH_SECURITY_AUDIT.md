# Authentication Security Audit

Last audit date: 2026-04-23 (phase 6 security hardening refresh). Re-checked
against core 2.24.0 on 2026-10-04: the module-boundary, event-name, test-path and
replay-evidence sections below were corrected to what that release does.

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
- The `agent` role was retired along with the (now-discontinued) cluster agent product; `policy:write` remains a valid permission and is granted by the built-in `admin` and `provider-admin` roles.

### Browser CSRF Defense

- CSRF enforcement is intentionally scoped to browser-style session suspension requests.
- `POST /sessions/{session_id}/suspend` requires `X-Requested-With` only when the request looks browser-originated (`Origin`, `Referer`, or `Cookie` present).
- API key clients, bearer-token clients, and non-browser API callers bypass the CSRF check.
- This keeps REST API automation compatible while still defending against browser-triggered session suspension.

### WebSocket Security

- Authentication failures close the socket with code `1008` before `websocket.accept()`, so the client sees the handshake refused (uvicorn answers it as HTTP `403`) and the connection is never used.
- `Origin` validation happens before `websocket.accept()` to mitigate cross-site WebSocket hijacking.
- The WebSocket endpoints need a WebSocket library in the environment. The container image installs `websockets`; a `pip`/`uv` install of 2.24.0 does not, and there the upgrade is never served -- the request is answered as plain HTTP (`401` without credentials) ([mcp-hangar/mcp-hangar#1676](https://github.com/mcp-hangar/mcp-hangar/issues/1676)).
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

Open defects in this audit's scope, filed publicly:

- A `tools:` access policy with one invalid field is dropped whole with only a warning, so the gateway enforces no policy for that server -- denied and approval-listed tools run ([mcp-hangar/mcp-hangar#1648](https://github.com/mcp-hangar/mcp-hangar/issues/1648)).
- The auth routes take `assigned_by` / `created_by` / `revoked_by` / `updated_by` from the request body, so the actor recorded for a key or role change is caller-supplied ([mcp-hangar/mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)).
- `/config/diff` and `/config/backup` accept a `config_path` and ignore `--config` ([mcp-hangar/mcp-hangar#1652](https://github.com/mcp-hangar/mcp-hangar/issues/1652)).
- `oidc.clock_skew_leeway_seconds` is never parsed ([mcp-hangar/mcp-hangar#1654](https://github.com/mcp-hangar/mcp-hangar/issues/1654)).
- A global `developer` can withdraw or restore a tool for all tenants ([mcp-hangar/mcp-hangar#1656](https://github.com/mcp-hangar/mcp-hangar/issues/1656)).
- An explicit `--config` / `MCP_CONFIG` path that does not exist boots a demo configuration ([mcp-hangar/mcp-hangar#1650](https://github.com/mcp-hangar/mcp-hangar/issues/1650)) -- confirm the path exists before starting; and a bare `mcp-hangar` ignores `MCP_HTTP_HOST` / `MCP_HTTP_PORT` ([mcp-hangar/mcp-hangar#1651](https://github.com/mcp-hangar/mcp-hangar/issues/1651)) -- start with `mcp-hangar serve` and an explicit `--host`.
