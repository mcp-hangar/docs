# 19 -- Canary Group Routing

> **Prerequisite:** [05 -- Load Balancing](05-load-balancing.md) (canary routing extends groups and load balancing; see also [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md) for tenant identity)
> **You will need:** MCP Hangar 1.4.0, two versions of a backend MCP server, an OIDC issuer minting JWTs with a `tenant_id` claim
> **Time:** ~15 minutes
> **Adds:** Per-tenant canary and version routing for groups (pins + sticky split + LB fallback)

## The Problem

You have a new version of a backend MCP server and you want to roll it out
safely, not flip every caller at once. A blanket weighted split sends a random
slice of every request to the new version, but it is not stable -- the same
tenant can land on v1 on one call and v2 on the next, which makes bug reports
and migrations hard to reason about.

What you actually want is identity-driven rollout. A handful of named tenants
(your beta partners) should always land on the new version. A deterministic
percentage of everyone else should be pinned to the canary so a given tenant
always gets the same version. And if the new version is unhealthy, traffic must
fall back to the load balancer rather than route into a dead member.

Hangar 1.4 adds a `canary:` block on a group that does exactly this: explicit
tenant pins, a sticky percentage split keyed on tenant identity, and a safe
fallback to the group's normal load-balancing strategy.

## The Config

Canary routing needs a tenant identity to key on, so this recipe reuses the
front-door auth setup from recipe 16 to put a `tenant_id` on every caller. The
new part is the `search` group and its `canary:` block.

```yaml
# config.yaml -- Recipe 19: Canary Group Routing

tool_access:
  mode: front_door                       # from recipe 16: face callers, fail-closed

auth:                                     # from recipe 16: validate JWTs, set tenant_id
  enabled: true
  allow_anonymous: false
  oidc:
    enabled: true
    issuer: https://auth.example.com
    audience: mcp-hangar
    resource_uri: https://hangar.example.com
    tenant_claim: tenant_id              # JWT claim -> CallerIdentity.tenant_id

mcp_servers:
  search:
    mode: group
    strategy: weighted_round_robin       # group's normal LB for everyone else
    min_healthy: 1
    description: "Search backend with canary rollout"

    canary:                              # NEW: per-tenant canary routing
      member: search-v2                  # NEW: member that receives canary traffic
      split_pct: 10                      # NEW: 10% of tenants pinned to search-v2
      pinned_tenants:                    # NEW: explicit tenant -> member pins
        "tenant:beta": search-v2         # NEW: beta partner always on the new version
        "tenant:legacy": search-v1       # NEW: legacy tenant held on the old version

    members:
      - id: search-v1                    # stable version
        mode: remote
        endpoint: https://search-v1.example.com/mcp
        weight: 90
      - id: search-v2                    # canary version
        mode: remote
        endpoint: https://search-v2.example.com/mcp
        weight: 10
```

Save this as `~/.config/mcp-hangar/config.yaml` or pass it with `--config`.

## Try It

1. Start Hangar with the group and auth

   ```bash
   mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve \
     --http --host 0.0.0.0 --port 8000
   ```

   With `auth.oidc.tenant_claim: tenant_id`, every authenticated call carries a
   `CallerIdentity.tenant_id`, which is what the `canary:` block routes on. (No
   tenant identity means no canary -- see step 5 and "What Just Happened".)

1. Call as a pinned tenant (`tenant:beta` -> search-v2)

   Obtain a JWT from your IdP whose `tenant_id` claim is `tenant:beta`, then call
   a tool on the `search` group. `tenant:beta` is pinned to `search-v2`, so the
   call always lands on the new version regardless of `split_pct` or weights.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_BETA_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"version","arguments":{}},"id":1}' \
     | jq '.result'
   ```

   The cleanest way to observe which member served the call is to have the tool
   report its own version. Expected output (assuming a `version` tool on the
   backend):

   ```json
   {"version": "search-v2"}
   ```

   If your backends do not expose a version tool, watch the Hangar logs instead.
   An illustrative routing line for this call looks like:

   ```text
   group=search tenant=tenant:beta route=pinned member=search-v2
   ```

   (Field names are illustrative -- check your own logs for the exact format.)

1. Call as a pinned tenant (`tenant:legacy` -> search-v1)

   Now call with a JWT whose `tenant_id` is `tenant:legacy`. That tenant is
   pinned to `search-v1`, so it is held on the old version even though `search-v2`
   is taking canary traffic for others.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_LEGACY_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"version","arguments":{}},"id":1}' \
     | jq '.result'
   ```

   Expected output:

   ```json
   {"version": "search-v1"}
   ```

   Explicit pins always win, in either direction -- use them to opt a partner
   into the canary or to hold a fragile tenant back on the stable version.

1. Call as several ordinary tenants (sticky split)

   Tenants that are not pinned go through the split. With `split_pct: 10`, about
   one in ten tenant IDs is routed to `search-v2`; the rest follow the group's
   `weighted_round_robin` strategy. Loop a few unpinned tenants and record where
   each lands.

   ```bash
   for t in tenant:001 tenant:002 tenant:003 tenant:004 tenant:005; do
     jwt=$(mint-jwt --tenant "$t")        # your IdP / test helper
     ver=$(curl -s http://localhost:8000/mcp \
       -H "Authorization: Bearer $jwt" \
       -H "Content-Type: application/json" \
       -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"version","arguments":{}},"id":1}' \
       | jq -r '.result.version')
     echo "$t -> $ver"
   done
   ```

   Expected output (which specific tenants land on the canary depends on their
   IDs, not on call order):

   ```text
   tenant:001 -> search-v1
   tenant:002 -> search-v2
   tenant:003 -> search-v1
   tenant:004 -> search-v1
   tenant:005 -> search-v1
   ```

   The key property is **determinism**: rerun the loop and every tenant lands on
   the same version as before. Hangar buckets a tenant with
   `SHA-256(tenant_id) % 100` and routes to the canary when the bucket is less
   than `split_pct` (so `split_pct: 10` means buckets `0`--`9`). Because it uses a
   stable hash rather than the process-local `hash()`, the same tenant lands in
   the same bucket on every worker and after every restart.

1. Show the fallback (canary member unhealthy)

   Take `search-v2` out of rotation -- stop the backend on
   `https://search-v2.example.com/mcp`, or let it fail enough health checks to be
   removed. Now repeat the `tenant:beta` call from step 2.

   ```bash
   curl -s http://localhost:8000/mcp \
     -H "Authorization: Bearer $TENANT_BETA_JWT" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"version","arguments":{}},"id":1}' \
     | jq '.result'
   ```

   Even though `tenant:beta` is pinned to `search-v2`, the call is now served by
   the load balancer -- which picks the only healthy member, `search-v1`:

   ```json
   {"version": "search-v1"}
   ```

   Hangar emits an illustrative fallback warning:

   ```text
   WARNING canary target search-v2 not in rotation; falling back to load balancer
   ```

   (Message text is illustrative.) When `search-v2` recovers and re-enters
   rotation, `tenant:beta` is pinned back to it automatically -- no config change
   or restart required.

## What Just Happened

Canary routing runs inside `select_member_for(tenant_id)`, before the group's
load-balancing strategy. For each call it resolves a member in a fixed order:

1. **Explicit pin.** If `canary.pinned_tenants` has an entry for this
   `tenant_id`, that member wins outright. This is what sends `tenant:beta` to
   `search-v2` and holds `tenant:legacy` on `search-v1`.
2. **Sticky split.** Otherwise Hangar computes `bucket = SHA-256(tenant_id) % 100`
   and, if `bucket < split_pct`, routes to `canary.member`. The comparison is a
   strict `<`, so `split_pct: 10` covers buckets `0`--`9` -- exactly 10% of the
   bucket space.
3. **Load balancer.** Anything that is neither pinned nor in the split bucket
   falls through to the configured group `strategy` (here
   `weighted_round_robin`).

The split is deterministic and cross-process-stable on purpose. Hangar hashes
the tenant ID with `hashlib.sha256` rather than Python's built-in `hash()`,
whose seed varies per process. That means a given tenant lands in the same
bucket on every Hangar worker and across restarts, so a tenant in the canary
slice keeps seeing the canary version until you change the policy -- "sticky"
canary rather than per-request roulette.

Canary routing is tenant-driven, so it only fires when there is a tenant to key
on. A call with no caller identity (an internal selection with no tenant, the
non-tenant `select_member()` path) skips canary entirely and goes straight to
the load balancer. That is why the front-door `auth.oidc.tenant_claim` from
recipe 16 is a prerequisite: no `tenant_id`, no pins, no split.

The fallback is what makes this safe to leave on during a rollout. If the pinned
or canary member is not `in_rotation` -- unhealthy, or removed by the group's
health policy -- Hangar logs the fallback and asks the load balancer for a
healthy member instead. It never routes to a member that is out of rotation,
even for an explicitly pinned tenant. The pin re-applies on its own once the
member is healthy again.

Finally, the `canary:` block is validated at config load with warn-and-skip
semantics, so a typo degrades the canary instead of crashing the server. A
`split_pct` outside `0`--`100` is reset to `0` with a warning; a `canary.member`
that is not a member of the group is cleared with a warning; and a
`pinned_tenants` entry pointing at a non-member (or with the wrong type) is
skipped with a warning. In every case the group keeps serving from its normal
load balancer.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `canary.member` | string | -- | Group member ID that receives canary traffic. Cleared with a warning if it is not a member of the group. Requires a tenant ID on the call to take effect. |
| `canary.split_pct` | int | `0` | Deterministic percentage of tenants routed to `canary.member`, range `0`--`100`. Bucket is `SHA-256(tenant_id) % 100`; routed when `bucket < split_pct`. Out-of-range values reset to `0` with a warning. Requires a tenant ID. |
| `canary.pinned_tenants` | dict (tenant ID -> member ID) | `{}` | Explicit tenant-to-member pins; checked before the split and always win. Entries pointing at a non-member or with the wrong type are skipped with a warning. Requires a tenant ID. |

All three keys require a `tenant_id` on the caller -- enable an OIDC auth setup
with `tenant_claim` (recipe 16) so Hangar can populate `CallerIdentity.tenant_id`.
Without a tenant ID, the whole `canary:` block is bypassed and the group uses its
load-balancing `strategy`.

## What's Next

For the conceptual model of groups, the load-balancing strategies behind the
fallback, and the canary resolution order in context, see the
[Per-Tenant Canary Routing](../guides/MCP_SERVER_GROUPS.md#per-tenant-canary-routing)
section of the MCP Server Groups guide. For the full YAML schema of every
`canary:` and group key, see the
[Configuration Reference](../reference/configuration.md).
