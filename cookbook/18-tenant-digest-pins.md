# 18 -- Per-Tenant Digest Pins

> **Prerequisite:** [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md)
> **You will need:** MCP Hangar 1.4.0, an OIDC issuer minting JWTs with a `tenant_id` claim, a backend whose tool schema you can pin
> **Time:** ~20 minutes
> **Adds:** Per-tenant digest pins on the call path, per-server enforcement modes (audit/warn/block)

## The Problem

The same back-end tool can mean different things to different tenants. One
tenant has reviewed and approved an exact `refund` schema and wants any drift to
be rejected before the call ever reaches the backend. Another tenant has not
pinned anything and just wants the tool to keep working. A single global digest
policy cannot express both at once.

Hangar 1.4 lets you pin a tool's schema digest **per tenant** and enforce it on
the live invocation path. The pin only applies to callers whose JWT carries the
matching `tenant_id`, so one tenant gets strict integrity while another is
unaffected. Enforcement is scoped per MCP server and rolls out safely through
`audit` -> `warn` -> `block`, so you can observe the real digest before you turn
on blocking.

## The Config

This recipe builds on the front-door setup from Recipe 16. We reuse
`tool_access.mode: front_door` and the OIDC `tenant_claim` so the front door can
deliver a `tenant_id`; without an authenticated tenant identity, a per-tenant
pin can never apply.

The new surface is `tool_projection.tenant_overrides.<tenant>.pins`: a map of
tool name to a 64-character lowercase hex SHA-256 digest. We start enforcement
in `audit` so the call passes while we capture the observed digest.

```yaml
# config.yaml -- Recipe 18: Per-Tenant Digest Pins

tool_access:
  mode: front_door                       # reuse front-door topology (Recipe 16)

auth:                                     # validate JWTs; Hangar does not issue them
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    issuer: https://auth.example.com
    audience: mcp-hangar
    resource_uri: https://hangar.example.com
    tenant_claim: tenant_id               # JWT claim -> CallerIdentity.tenant_id

mcp_servers:
  payments:
    mode: remote
    endpoint: http://localhost:8080/mcp
    description: "Payments backend"

    tool_projection:
      digest_enforcement: audit           # NEW: start in audit (observe, do not block)

      withdrawn: []                       # (optional) tools withdrawn for ALL tenants

      tenant_overrides:
        "tenant:a":
          # NEW: pin refund for tenant:a only.
          # Placeholder digest -- replace with the OBSERVED digest in Try It.
          pins:
            refund: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
          # withdrawn: [beta_tool]        # (optional) per-tenant withdrawal
```

Save this as `~/.config/mcp-hangar/config.yaml` or pass it with `--config`.

`digest_enforcement` is scoped per MCP server: setting it on `payments` does not
change enforcement on any other server. When you do not set it at all, the
default for that server is `block`. We set it explicitly to `audit` here only
for the observe-first rollout below.

A note on `withdrawn`: `tool_projection.withdrawn` removes a tool for every
tenant, and `tenant_overrides.<tenant>.withdrawn` removes it for one tenant.
Those are separate from pinning and are shown only for completeness -- this
recipe is about pins.

## Try It

1. Start Hangar in audit mode

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 0.0.0.0 --port 8000
   ```

   With `digest_enforcement: audit`, a digest that does not match the pin is
   allowed through and recorded -- nothing is blocked yet. This is the safe
   window to discover the real digest.

1. Call `refund` as `tenant:a` and observe the audited digest

   Obtain a JWT from your IdP whose `tenant_id` claim is `tenant:a`, then invoke
   the tool. In front-door mode external agents see the flat back-end tool name
   `refund`, not the `hangar_*` meta-API.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_A_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"refund","arguments":{}},"id":1}' \
     | jq '.result // .error'
   ```

   In `audit` the call succeeds. Because the placeholder pin almost certainly
   does not match the live schema, Hangar records a mismatch for review. A
   `DigestMismatchEvent` carrying `tenant_id: tenant:a` is emitted whenever the
   computed schema digest differs from the pin. Inspect your log/metrics sink
   for that event to read the observed digest, for example (illustrative only --
   exact log strings vary by sink):

   ```text
   # illustrative -- format depends on your logging backend
   DigestMismatchEvent mcp_server=payments tool=refund tenant_id=tenant:a \
     pinned=0123...cdef observed=9f2b...a17c enforcement=audit
   ```

   The `observed` value is the canonical digest of the tool's current schema
   (RFC 8785 JCS + SHA-256, with `None`, `{}`, `[]`, and `""` treated as
   absent). That is the value you pin.

   If you prefer to compute the digest directly from the backend's advertised
   schema instead of reading it off an event, hash the tool entry with the same
   canonicalization Hangar uses:

   ```bash
   python - <<'PY'
   from mcp_hangar.domain.services.digest_computation import compute_tool_digest

   # paste the tool entry exactly as the backend advertises it
   refund = {
       "name": "refund",
       "description": "Refund a payment",
       "inputSchema": {"type": "object", "properties": {}},
   }
   print(compute_tool_digest(refund).sha256)
   PY
   ```

   Expected output: a single 64-character lowercase hex digest.

   ```text
   9f2b1c0d...a17c
   ```

1. Pin the observed digest and switch to `block`

   Replace the placeholder pin with the observed digest and change enforcement
   from `audit` to `block`.

   ```diff
     tool_projection:
   -   digest_enforcement: audit
   +   digest_enforcement: block
       tenant_overrides:
         "tenant:a":
           pins:
   -         refund: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
   +         refund: 9f2b1c0d...a17c
   ```

   Make sure the value you paste is exactly 64 lowercase hex characters
   (`[0-9a-f]{64}`). If it is not, Hangar warn-skips that pin when it loads the
   config -- it does not crash, and the tool simply runs unpinned.

   Reload the config (hot-reload if you have it wired up, otherwise restart):

   ```bash
   # hot-reload
   curl -s -X POST http://localhost:8000/api/config/reload -H "X-API-Key: <admin-key>" | jq
   # or just restart the serve process
   ```

   Now call `refund` again as `tenant:a`:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_A_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"refund","arguments":{}},"id":2}' \
     | jq '.result // .error'
   ```

   Expected: the call succeeds. The live schema digest matches the pin, so even
   under `block` the invocation is allowed and no mismatch event is emitted.

1. Simulate schema drift and confirm `tenant:a` is blocked

   Change the `refund` schema on the backend (add a required field, rename a
   property, change a type -- anything that alters the canonical schema). Then
   call `refund` again as `tenant:a` with enforcement still set to `block`:

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_A_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"refund","arguments":{}},"id":3}' \
     | jq '.result // .error'
   ```

   Expected: the call is rejected. The new schema digest no longer matches the
   pin, so under `block` Hangar refuses the invocation and emits a
   `DigestMismatchEvent` carrying `tenant_id: tenant:a`. The response surfaces as
   a call error rather than a tool result (the exact error envelope depends on
   your transport; the key fact is that the call is blocked before it reaches the
   backend).

1. Call `refund` as `tenant:b` and confirm it is unaffected

   Obtain a JWT whose `tenant_id` claim is `tenant:b`. `tenant:b` has no pin for
   `refund`, so the per-tenant pin does not apply to it at all -- the same drift
   that blocks `tenant:a` is irrelevant here.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_B_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"refund","arguments":{}},"id":4}' \
     | jq '.result // .error'
   ```

   Expected: the call succeeds, drift or no drift. A pin only constrains the
   tenant it is declared under.

## What Just Happened

A per-tenant pin lives at
`tool_projection.tenant_overrides.<tenant>.pins.<tool>` and is just the expected
canonical digest of that tool's schema. On the live call path Hangar resolves
the caller's `tenant_id` (from the JWT `tenant_claim`, default `tenant_id`),
looks up a pin for the requested tool under that tenant, computes the current
schema digest, and compares. The pin is consulted **only** when the caller has a
matching `tenant_id`; an anonymous caller, or a tenant with no pin entry, falls
through to the normal projection and withdrawal logic. That is why `tenant:b`
sailed through the same drift that stopped `tenant:a`.

The digest itself is computed from the canonical tool schema: RFC 8785 JSON
Canonicalization Scheme, then SHA-256. The empty optional values `None`, `{}`,
`[]`, and `""` are treated as absent, so a backend that sends an empty
`annotations: {}` and one that omits it produce the same digest. The pin you
store is exactly the value that canonical computation should yield for the
approved schema. A pin that is not a 64-character lowercase hex string is
warn-skipped at config load -- the rest of the config still loads, and that one
tool runs unpinned.

`digest_enforcement` decides what happens on a mismatch, and it is scoped per
MCP server:

- `audit` -- allow the call and record the event for audit.
- `warn` -- allow the call and emit a warning.
- `block` -- reject the call when the schema does not match the pin.

When unset, a server defaults to `block`. Because it is per server, turning on
`block` for `payments` does not change enforcement for any other backend. Every
mismatch -- in any mode -- emits a `DigestMismatchEvent` that includes the
`tenant_id`, which is what made the audit-first rollout possible: we ran in
`audit` to capture the real `observed` digest, pinned it, and only then switched
to `block`.

The audit -> block sequence is the whole point. Pinning straight to `block`
against a digest you have not verified will reject the first legitimate call.
Observing in `audit`, copying the emitted digest into the pin, then flipping to
`block` gives you strict per-tenant integrity with zero guesswork.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tool_projection.digest_enforcement` | string | `block` | Per-MCP server mismatch handling: `audit`, `warn`, or `block` |
| `tool_projection.tenant_overrides.<tenant>.pins` | dict[str, str] | `{}` | Tool name to 64-char lowercase hex SHA-256 pin, applied only to that tenant |
| `tool_projection.tenant_overrides.<tenant>.withdrawn` | list | `[]` | Tools withdrawn for one tenant |
| `tool_projection.withdrawn` | list | `[]` | Tools withdrawn for all tenants |
| `auth.oidc.tenant_claim` | string | `tenant_id` | JWT claim mapped to `CallerIdentity.tenant_id` |
| `tool_access.mode` | string | `egress` | Topology mode; use `front_door` to face untrusted tenants |

Per-tenant pins are independent per MCP server, and a pin applies only when the
caller identity carries the matching `tenant_id`.

## What's Next

For the full background on digest pinning -- unknown-tool policy
(`allow_unverified`, with `allow_degraded` still accepted as a deprecated alias
in 1.4.0), mismatch enforcement levels, and the per-tenant pin schema -- see the
Digest Pinning section of the
[Configuration Reference](../reference/configuration.md).

If you are arriving here from an older release, recompute existing pins under the
RFC 8785 JCS algorithm first: see
[14 -- Upgrade: Digest Pinning](14-upgrade-1.3-digest-pinning.md).
