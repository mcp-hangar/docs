# ADR-009: Independent Release Topology -- Core, Operator Image, and OCI Helm Charts Release on Their Own SemVer

**Status:** Proposed
**Date:** 2026-07-14
**Authors:** MCP Hangar Team

## Context

The multi-repo split (see the vestigial `packages/core/` cleanup, `#466`) left
MCP Hangar's shippable artifacts spread across four repositories, each with its
own release machinery:

- **`mcp-hangar`** (Python core) -- `release-please` on `main` cuts a `vX.Y.Z`
  tag and GitHub release; the package publishes to PyPI. This is the one path
  that actually runs: `v1.4.0` is live, with a full tag history back to `v1.2.1`.
- **`mcp-hangar-operator`** (Go operator) -- `release.yml` triggers on
  `push` of a `v*.*.*` tag, builds a multi-arch image to
  `ghcr.io/mcp-hangar/mcp-hangar-operator`, and is expected to attach the
  rendered install manifest to the release.
- **`helm-charts`** (three charts: `mcp-hangar`, `mcp-hangar-operator`,
  `hangar-agent`) -- `release-charts.yml` triggers on `push` to `main` (and
  `workflow_dispatch`), `helm push`es each chart to
  `oci://ghcr.io/mcp-hangar/charts`, and is idempotent: a chart whose version
  already exists in the registry is skipped. The version is whatever each
  `Chart.yaml` declares -- there is no tag.
- **`docs`** -- carries a release hub / public install index and its own
  `release-please`, publishing a docs package on a `v*.*.*` tag.

**The topology is implemented in CI but has never been exercised.** A live
audit on 2026-07-14 confirms the earlier finding: `mcp-hangar-operator`,
`helm-charts`, and `docs` each have **zero tags, zero GitHub releases, and no
successful release workflow run**. GHCR package visibility, ownership,
retention, provenance, and signing could not be verified with the available
token. Only the Python core is proven end-to-end.

Two things force a decision now rather than later. First, `#453` (compatibility
matrix + GHCR security policy) and the first-release verification issues
(`mcp-hangar-operator#26`, `helm-charts#7`) are all blocked on a ratified
statement of *what the topology is*. Second, the core repo still carries
dormant operator/Helm CI it should not remove until this ADR says the
independent topology is the intended end state.

The question this ADR closes is narrow: **do core, operator image, and charts
release independently, each owning its own SemVer and its own artifacts -- or
does some coordinating repo own a unified version?** Everything else
(compatibility ranges, GHCR hardening, first-release proof) is downstream of
that answer and is delegated, not decided here.

## Decision

1. **Three independent release lanes, three owners, three SemVer lines.** The
   Python core, the operator image, and the Helm charts version and release
   independently. No repo owns a global "MCP Hangar version"; a deployment is a
   *set* of independently-versioned artifacts related by the compatibility
   matrix (`#453`), not by a shared tag.

2. **`mcp-hangar-operator` owns the operator image and its install manifest.**
   A `v*.*.*` tag on the operator repo is the single release trigger; it
   produces the multi-arch GHCR image **and** the rendered install manifest
   attached to that release. The operator's SemVer tracks the operator's own
   API/CRD surface, not the core.

3. **`helm-charts` owns the OCI chart artifacts.** Charts publish to
   `oci://ghcr.io/mcp-hangar/charts`, one OCI tag per `Chart.yaml` `version`.
   Each chart's `version` (the packaging SemVer) is independent of its
   `appVersion` (the component image it deploys): a chart-only fix bumps
   `version` without touching `appVersion`, and a new component image bumps
   `appVersion` (and, per SemVer, `version`). Publication is idempotent by
   design -- re-running never overwrites an existing OCI tag.

4. **`docs` owns the public install/release index -- but only advertises what
   is verified.** The release hub may list an install command
   (`helm install ... oci://...`, `kubectl apply -f <manifest-url>`, `pip
   install mcp-hangar==X.Y.Z`) **only after** the corresponding artifact has a
   verified published digest. Until then the index states the artifact is
   planned, not available. This is the async form of ADR-008's rule: do not
   advertise a capability that does not yet run.

5. **Release tags are immutable; consumers pin by digest.** Once a component
   version is released it is never re-published or moved. Image and chart
   consumers pin by digest (`@sha256:...`), consistent with ADR-004 (digest
   pinning). Mutable/rolling tags, if any exist, are conveniences layered on
   top of immutable digests, never the unit of trust.

6. **Status stays `Proposed` until the topology is proven.** This ADR is
   ratified to `Accepted` only when the initial-release gate below is met. It
   deliberately does **not** claim the topology is operational today, because
   it is not.

### Delegated to follow-ups (stated here as boundaries, decided there)

- **Compatibility matrix + CRD upgrade/rollback policy -> `#453`.** The ADR
  fixes the *shape* (core x operator x chart x Kubernetes ranges, with an owner
  and an update procedure); `#453` fills and maintains it. Independent SemVer is
  only safe *because* a compatibility matrix exists -- shipping the matrix is a
  precondition of declaring independent release "supported."
- **GHCR security policy -> `#453`.** Target posture to be verified, not
  assumed: packages public; release tags immutable; keyless (OIDC) `cosign`
  signatures + SBOM attestations attached; documented retention; consumer-side
  digest verification instructions. The ADR ratifies the *intent*; `#453` proves
  each property against the live registry.
- **First-release verification -> `mcp-hangar-operator#26`, `helm-charts#7`.**
  These cut and verify the first operator image/manifest and the first OCI
  charts, respectively, producing the digests the docs index needs.

### Initial-release gate (Proposed -> Accepted)

This ADR flips to `Accepted` only when all hold:

- [ ] `mcp-hangar-operator#26`: one verified operator image + manifest release,
      with a recorded digest.
- [ ] `helm-charts#7`: the three charts published to GHCR OCI, with recorded
      digests and a verified `helm pull`.
- [ ] `#453`: compatibility matrix published with an owner, and GHCR security
      posture verified against the live registry.
- [ ] `docs`: the release hub advertises only the verified artifacts.

Only after ratification should the core repo remove its dormant operator/Helm
CI, and only then should the docs index present install commands as supported.

## Consequences

- **Independent cadence, at the cost of a matrix.** Each component ships when it
  is ready; a core patch does not gate an operator release and vice versa. The
  price is that "which versions work together" stops being obvious from a shared
  number and must be answered by the `#453` matrix -- a real maintenance
  obligation, not a formality.
- **The operator and helm triggers are intentionally different, and that
  asymmetry is now on the record.** Operator releases are tag-gated (a
  deliberate, human-cut event, appropriate for a distributed binary image);
  charts publish idempotently on merge to `main`, keyed by `Chart.yaml`
  `version` (appropriate for text artifacts where the version bump *is* the
  release intent). This ADR ratifies the asymmetry rather than forcing
  uniformity -- see Open Questions for the fork the ratifier may still take.
- **Dormant CI stays dormant a little longer.** Core keeps its operator/Helm CI
  until the gate is met, because removing it before the independent lanes are
  proven would strand the fallback.
- **Docs can under-promise safely.** Because the index is gated on verified
  digests, a half-built topology cannot leak an install command that 404s or
  pulls a non-existent chart -- the failure mode the audit was worried about.
- **First release is a coordinated act, then never again.** Bootstrapping the
  first operator and chart releases (`#26`, `#7`) needs a maintainer with GHCR
  write and org context; steady-state releases afterward are per-repo and
  independent.

## Alternatives Considered

- **Unified monorepo version (one tag releases everything).** Rejected: it
  re-couples exactly what the multi-repo split decoupled, forces a core patch to
  re-release the operator and charts, and makes "core `1.4.1` with operator
  `1.4.0`" unexpressible -- the normal, healthy state of independent components.
- **`docs` (or a hub repo) owns and orchestrates all releases centrally.**
  Rejected: it puts release authority in the repo furthest from each artifact's
  build, and turns docs -- a *consumer* of verified digests -- into the
  *producer*, inverting the trust direction and coupling doc edits to artifact
  publication.
- **Force operator and charts onto one identical trigger.** Rejected for now
  (but see Open Questions): a binary image and a text chart have genuinely
  different release semantics; imposing one mechanism on both trades a real fit
  for a cosmetic symmetry. The asymmetry is ratified explicitly instead of by
  accident.

## Open Questions (to be closed by the ratifier before `Accepted`)

These are the sub-decisions the current CI answers *inconsistently or
implicitly*; the ADR records a recommended default for each, but the human
ratifier owns the final call.

1. **Chart release trigger -- keep the asymmetry or unify?** Operator is
   tag-gated; charts publish on merge to `main` from `Chart.yaml` `version`.
   *Recommended:* keep the asymmetry (Decision 3 / 2), but require a
   `Chart.yaml` version-bump check in chart-repo CI so an un-bumped chart change
   is a hard failure rather than a silent idempotent skip. Alternatively, move
   charts to `release-please` for uniformity with core/docs. **Ratifier picks.**
2. **`appVersion` <-> component coupling.** Recommended: chart `appVersion` =
   the released component version (image tag), chart `version` independent.
   Confirm this is the intended relationship for all three charts, including
   `hangar-agent`, whose component release lane is not otherwise covered here.
3. **Is `hangar-agent` a fourth release lane?** It has a chart but no image
   release lane described in the audit. Confirm whether the agent image
   releases independently (a fourth lane) or ships only bundled -- this ADR
   currently scopes three lanes plus a chart that references the agent.
4. **GHCR tag mutability + retention specifics** are delegated to `#453`;
   confirm the *intent* in Decision 5 (immutable release tags, digest-pinned
   consumption) is the posture `#453` should verify against.

## References

- Parent / ratification: `mcp-hangar/mcp-hangar#410` (proposed ADR-009),
  `mcp-hangar/docs#22` (this document).
- Follow-ups: `mcp-hangar-operator#26` (first image/manifest release),
  `mcp-hangar/helm-charts#7` (OCI chart policy + first release),
  `mcp-hangar/mcp-hangar#453` (compatibility matrix + GHCR security policy).
- Related: ADR-004 (digest pinning; the trust unit for released artifacts),
  ADR-008 (do-not-advertise-what-does-not-run; the sync analogue of Decision 4).
- Cleanup context: `mcp-hangar/mcp-hangar#466` (remove vestigial `packages/core/`).
- Workflows audited (2026-07-14): `mcp-hangar-operator/.github/workflows/release.yml`,
  `helm-charts/.github/workflows/release.yml`, `docs/.github/workflows/publish.yml`.
