# ADR-016: Approval Resolution Has One Authorized Chokepoint, and Core Knows No Vendors

**Status:** Accepted
**Date:** 2026-07-29
**Authors:** MCP Hangar Team
**Related:** [ADR-014](ADR-014-tasks-relay-with-governance.md) (task relay-with-governance), core#656, core#660, [modelcontextprotocol#2919](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2919).

## Context

Hangar had two disjoint mechanisms for human decisions.

`approvals/` holds a `tools/call` until an external approver decides, out of band, over a webhook and a REST endpoint. The MCP client sees nothing: it observes a slow tool, with no way to display, cancel, or attribute the wait. `TaskConsentGate` protects the mid-flight `input_required` step of a governed task, in the protocol, decided by the calling client.

These are not two layers of one thing. They are one need split by what the protocol can express. `inputRequests` is a closed union of three methods, two of which are `@deprecated` in the same 2026-07-28 revision; what remains is `elicitation/create`, which cannot say *someone other than the caller must approve this*. So the out-of-band half was built out of band, and the approvals layer survived the entire Tasks extension landing without a single line changing — it had nothing to attach to.

An audit of that untouched layer found two defects and one shape.

**Authorization was absent.** `approval:resolve` was defined in `auth/roles.py`, mapped from its string form, and granted to a role. Nothing checked it: `grep -rn "authorize" src/mcp_hangar/approvals/` returned nothing. Authentication is global, so a request needed a valid token — but any principal holding one could decide any approval given its id.

**Attribution was client-supplied.** `_extract_principal` looked for `request.state.principal_id` and fell back to the `x-principal-id` header, defaulting to `"unknown"`. That reads like a fallback for unauthenticated callers. It was the only path: the authentication middleware attaches `request.state.auth`, and nothing in the tree ever set `principal_id`. Every `decided_by` in the provenance chain was therefore either asserted by the caller or the literal string `"unknown"`.

**And the route let the caller choose its own authenticator.** `resolve_approval` branched on the presence of an `X-Slack-Signature` header into a vendor-specific verifier. Both branches were individually correct — HMAC-SHA256 over `v0:ts:body`, a 300s freshness window, `compare_digest`, a 500 when no secret is configured. This was not an open hole. It is a shape in which an unauthenticated caller decides which authentication mechanism runs, and it stays safe only while every branch behind it stays correct.

Underneath, `_build_delivery` hardcoded `if channel == "slack"` and imported `.delivery.slack`, putting one vendor's Block Kit payloads in the core tree. The *outbound* side was already behind an `ApprovalDelivery` protocol; the coupling was inbound.

## Decision

**1. Resolution goes through one command handler, and that handler authorizes.**

`ResolveApprovalCommand` carries an already-authenticated `Principal`; `ResolveApprovalHandler` checks `approval:resolve` before deciding anything. Transports parse and render; the handler decides.

The authorization deliberately does **not** live in the route, which is where the rest of the REST API puts it (`server/api/mcp_servers.py`). A second transport is coming: when approvals fold onto the governed-task path, the decision arrives as `tasks/update`, not as an HTTP request. A route-level guard would have to be duplicated there — and a guard that must be remembered twice is precisely what produced the missing check in the first place. One chokepoint means a new transport inherits authorization by construction rather than by review.

**2. Identity comes from the authenticated context, or the request is refused.**

`get_principal_from_request` — already present in `auth/http_middleware.py`, and already correct — replaces the hand-rolled reader. No header is ever consulted. `"unknown"` is unreachable.

**3. Auth-disabled deployments still resolve, attributed to the system principal.**

Requiring a principal unconditionally would 401 every resolution on an auth-off gateway, because the API router does not mount authentication there at all — no credential could ever satisfy it. That is the trade this codebase already got wrong once (core#600): failing closed on the API means failing **open** on enforcement, because the decision simply never gets made. The identity recorded is the system principal: explicit, server-side, and impossible to mistake for a real approver.

**4. Core knows no vendors. Adapters are installed, not imported.**

The `X-Slack-Signature` branch is removed; the route has one authentication path. Delivery channels resolve through the `mcp_hangar.approvals.delivery` entry-point group, with `dashboard` and `noop` shipped by core. A vendor adapter terminates the webhook itself — verifies the vendor signature, maps the vendor identity onto a Hangar principal, calls `POST /approvals/{id}/resolve` with an ordinary token.

A **reference** adapter ships in the docs rather than as a published package. Publishing one under the organization would make it ours to version, release, and keep working against a third party's API — a maintenance commitment taken on to demonstrate a boundary, which undercuts the boundary.

**5. An unknown or broken channel degrades; it does not stop the gateway.**

`noop` plus a warning. Approvals then queue undelivered but remain resolvable over the REST API, which an operator can recover from. Refusing to boot because a *notification* channel is missing converts a degraded path into an outage.

## Consequences

Provenance now names a Hangar principal. `decided_by = f"slack:{user_id}"` is gone: the vendor identity is mapped before it reaches the audit trail, so the chain is expressed in one namespace instead of leaking a third party's handles into it.

**This is a breaking change** for any deployment with `approvals.channel: slack`. It is taken at a major on purpose. The alternative — a deprecation shim for one cycle — means carrying two authentication paths in the route for another release, which is the exact shape being removed.

The pending-approval model is being reshaped (A-2919 WS-5) so that it serializes to something that could be a value inside `inputRequests`. That is deliberate sequencing, not speculation: the argument being made upstream in modelcontextprotocol#2919 is that the protocol should be able to express *a third party must approve this*. Rebuilding our own mechanism into the shape we are asking for comes first. Asking for a feature one does not use is the weaker position.

If #2919 lands in a different shape, we migrate an internal namespace — cheap, and entirely ours. If it does not land, the work above still stands on its own: it fixed a missing authorization check, an unattributable audit record, and a vendor dependency in the core tree.

## Alternatives Considered

**Authorize in the route, like the rest of the REST API.** Consistent, and wrong here for the reason in Decision 1: it does not survive a second transport.

**Keep the Slack branch behind a deprecation shim.** Gentler for existing users, and it preserves the header-chooses-authenticator shape for another cycle. A major release is the one moment this costs nothing.

**Publish `mcp-hangar-slack`.** More convenient for users. It also makes a vendor integration a first-party artifact with a release cadence, which is the coupling this ADR removes, relocated rather than resolved.

**Raise on an unknown channel.** Louder, and it fails in the wrong direction — see Decision 5 and core#600.

## References

- core#656 — authorization and attribution (WS-0, WS-1, WS-2)
- core#660 — vendors out of core (WS-3, WS-4)
- core#600 — failing closed on the API is failing open on enforcement
- [ADR-014](ADR-014-tasks-relay-with-governance.md) — the governed-task path approvals will fold onto
- [modelcontextprotocol#2919](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2919)
