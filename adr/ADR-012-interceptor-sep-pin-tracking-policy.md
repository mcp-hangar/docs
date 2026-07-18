# ADR-012: Interceptor SEP-Pin Tracking Policy

**Status:** Accepted
**Date:** 2026-07-18
**Authors:** MCP Hangar Team
**Related:** ADR-005 (SEP-1763 interceptor compliance), superseded by ADR-010. The in-process interceptor surface survived that retirement; this ADR governs how its upstream pin is tracked.

## Context

The in-process interceptor surface (`interceptors/list`, `interceptor/invoke`) validates against a JSON Schema we **maintain locally**, derived by hand from an unmerged, experimental upstream: `modelcontextprotocol/experimental-ext-interceptors @ 99bc7c9` (tracking **SEP-2133**, formerly SEP-1763). The upstream repo publishes no machine-readable schema, so the local `INTERCEPTOR_SCHEMA` mirrors the spec at the pinned commit.

That target is moving:

- The SEP **renumbered** under us -- SEP-1763 -> SEP-2133 -- and the capability key changed (`sep-2624` -> `io.modelcontextprotocol/interceptors`), each reconciled by hand (#401 / #405).
- The pin has already been bumped once (`5bd7ab4` -> `99bc7c9`, "6 commits ahead") and upstream notes the "wire format may still move."

Reactively re-pinning on every upstream commit is an unbounded recurring cost with surprise-breakage timing -- "three SEP iterations from now this is an unplanned weekend." ADR-005, which introduced interceptor compliance, is **superseded by ADR-010** (the agent + cloud tier retirement); ADRs are immutable, and the in-process surface that survived ADR-010 needs its own pin-policy record. Hence this ADR.

## Decision

1. **Vendor + freeze at a known-good SHA.** The locally-maintained schema is the single source of truth; it is derived from `experimental-ext-interceptors @ 99bc7c9` (SEP-2133). We never fetch upstream at runtime.
2. **Bump on a deliberate cadence, not reactively.** The pin moves only as a conscious decision -- review the upstream diff and re-derive the schema together -- never automatically on each upstream commit.
3. **Keep the surface explicitly experimental and off-by-default.** It is capability-negotiated (`io.modelcontextprotocol/interceptors`); absent negotiation it is inert. The contract is: *experimental, may break on an upstream move.*
4. **Scheduled drift detection.** A weekly CI check compares the pinned SHA to upstream `HEAD` and files an informational issue when they diverge, so a re-pin is a planned decision rather than a forced one. The canonical pinned SHA lives in the drift-check workflow (`.github/workflows/interceptor-pin-drift.yml`); moving it and re-deriving the vendored schema happen together.
5. **Revisit toward a hard freeze** once the SEP reaches an accepted / stable state -- then hold the pin and stop tracking movement entirely.

## Consequences

- Release health is **decoupled from upstream churn**: an upstream advance no longer forces an unplanned reconcile inside a release.
- The interceptor surface stays behind capability negotiation; consumers opt in and accept the experimental contract.
- **Cost (accepted):** the vendored schema may lag upstream between deliberate bumps. That is fine for an off-by-default, negotiated, experimental feature.
- The drift check may open a chore issue periodically -- that is the intended controlled signal, not noise to suppress.

## References

- Decision issue: mcp-hangar#488. Prior reconciles: #401, #405.
- Superseded predecessor: [ADR-005](ADR-005-sep-1763-interceptor-compliance.md) -> [ADR-010](ADR-010-retire-agent-cloud-tier.md).
- Affected surface (core): `src/mcp_hangar/fastmcp_server/interceptors_list.py`, `tests/unit/test_interceptors_list_schema.py`, `tests/unit/test_interceptor_invoke.py`.
