# ADR-009: Independent Release Topology -- Core, Operator Image, Agent Image, and OCI Helm Charts Release on Their Own SemVer

**Status:** Accepted — partially superseded by [ADR-010](ADR-010-retire-agent-cloud-tier.md) (the agent image lane is retired; four lanes become three)
**Date:** 2026-07-14
**Authors:** MCP Hangar Team

## Context

The multi-repo split (see the vestigial `packages/core/` cleanup, `#466`) left
MCP Hangar's shippable artifacts spread across several repositories, each with
its own release machinery:

- **`mcp-hangar`** (Python core) -- `release-please` on `main` cuts a `vX.Y.Z`
  tag and GitHub release; the package publishes to PyPI. This is the one path
  that actually runs: `v1.4.0` is live, with a full tag history back to `v1.2.1`.
- **`mcp-hangar-operator`** (Go operator) -- `release.yml` triggers on
  `push` of a `v*.*.*` tag, builds a multi-arch image to
  `ghcr.io/mcp-hangar/mcp-hangar-operator`, and attaches the rendered install
  manifest to the release.
- **`mcp-hangar-agent`** (Go sidecar) -- deployed in customer clusters via the
  `hangar-agent` chart. The agent image is a distinct artifact on its own
  SemVer, but its repository has **no release workflow yet** (see Consequences).
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
successful release workflow run**; the agent has no release workflow at all.
GHCR package visibility, ownership, retention, provenance, and signing could
not be verified with the available token. Only the Python core is proven
end-to-end.

Two things forced this decision now. First, `#453` (compatibility matrix +
GHCR security policy) and the first-release verification issues
(`mcp-hangar-operator#26`, `helm-charts#7`) are all blocked on a ratified
statement of *what the topology is*. Second, the core repo still carries
dormant operator/Helm CI it should not remove until this ADR names the
independent topology as the intended end state.

The narrow question this ADR closes: **do core, operator image, agent image,
and charts release independently, each owning its own SemVer and its own
artifacts -- or does a coordinating repo own a unified version?** Everything
else (compatibility ranges, GHCR hardening, first-release proof) is downstream
of that answer and is delegated, not decided here.

## Decision

1. **Four independent release lanes, per-repo owners, independent SemVer
   lines.** The Python core, the operator image, the agent image, and the Helm
   charts version and release independently. No repo owns a global "MCP Hangar
   version"; a deployment is a *set* of independently-versioned artifacts
   related by the compatibility matrix (`#453`), not by a shared tag.

   | Lane | Owner repo | Trigger (as decided) | Artifact |
   |------|-----------|----------------------|----------|
   | Core | `mcp-hangar` | `release-please` -> `vX.Y.Z` tag | PyPI package |
   | Operator image + manifest | `mcp-hangar-operator` | `push` tag `v*.*.*` | multi-arch GHCR image + install manifest |
   | Agent image | `mcp-hangar-agent` | `push` tag `v*.*.*` (workflow to be authored) | multi-arch GHCR image |
   | OCI Helm charts | `helm-charts` | `push` to `main`, idempotent, per `Chart.yaml` `version` | 3 charts -> `oci://ghcr.io/mcp-hangar/charts` |

2. **`mcp-hangar-operator` owns the operator image and its install manifest.**
   A `v*.*.*` tag is the single release trigger; it produces the multi-arch
   GHCR image **and** the rendered install manifest attached to that release.
   The operator's SemVer tracks the operator's own API/CRD surface, not the core.

3. **`mcp-hangar-agent` owns the agent image (fourth lane).** The agent image
   releases independently on its own SemVer, tag-triggered, mirroring the
   operator lane. This lane is **ratified but not yet built**: the agent repo
   has no `release.yml` today, so authoring it is an explicit follow-up.

4. **`helm-charts` owns the OCI chart artifacts, and the asymmetry with the
   image lanes is deliberate.** Charts publish to `oci://ghcr.io/mcp-hangar/charts`,
   one OCI tag per `Chart.yaml` `version`. The image lanes are tag-gated (a
   deliberate, human-cut event, appropriate for a distributed binary); the
   chart lane publishes idempotently on merge to `main` (appropriate for a text
   artifact where the `Chart.yaml` version bump *is* the release intent). This
   asymmetry is ratified, not an accident. To make the chart lane safe, its CI
   **must fail a chart change that does not bump `Chart.yaml` `version`**, so an
   un-bumped edit is a hard error rather than a silent idempotent skip.

5. **Chart `version` and `appVersion` are decoupled.** Each chart's `version`
   (packaging SemVer) is independent of its `appVersion`, and `appVersion`
   equals the released component image version the chart deploys. A chart-only
   fix bumps `version` without touching `appVersion`; a new component image
   bumps `appVersion` (and, per SemVer, `version`). Publication is idempotent --
   re-running never overwrites an existing OCI tag.

6. **`docs` owns the public install/release index -- but only advertises what
   is verified.** The release hub may list an install command
   (`helm install ... oci://...`, `kubectl apply -f <manifest-url>`, `pip
   install mcp-hangar==X.Y.Z`) **only after** the corresponding artifact has a
   verified published digest. Until then the index states the artifact is
   planned, not available. This is the async form of ADR-008's rule: do not
   advertise a capability that does not yet run.

7. **Release tags are immutable; consumers pin by digest.** Once a component
   version is released it is never re-published or moved. Image and chart
   consumers pin by digest (`@sha256:...`), consistent with ADR-004 (digest
   pinning). Mutable/rolling tags, if any exist, are conveniences layered on top
   of immutable digests, never the unit of trust. Verifying that GHCR actually
   enforces immutability and the rest of the security posture is delegated to
   `#453`.

### Delegated to follow-ups (boundaries stated here, decided there)

- **Compatibility matrix + CRD upgrade/rollback policy -> `#453`.** The ADR
  fixes the *shape* (core x operator x agent x chart x Kubernetes ranges, with
  an owner and an update procedure); `#453` fills and maintains it. Independent
  SemVer is only safe *because* a compatibility matrix exists -- shipping the
  matrix is a precondition of declaring independent release "supported."
- **GHCR security policy -> `#453`.** Target posture to be verified, not
  assumed: packages public; release tags immutable (Decision 7); keyless (OIDC)
  `cosign` signatures + SBOM attestations attached; documented retention;
  consumer-side digest verification instructions.
- **First-release verification -> `mcp-hangar-operator#26`, `helm-charts#7`**,
  plus authoring the agent lane's release workflow. These cut and verify the
  first artifacts, producing the digests the docs index needs.

### Ratified sub-decisions (2026-07-14)

The four sub-decisions the CI previously answered inconsistently were ratified
by the maintainer and folded into the Decision above:

1. **Chart trigger asymmetry:** kept (Decision 4), with a mandatory
   `Chart.yaml` version-bump CI guard added.
2. **`appVersion` coupling:** confirmed -- `appVersion` = released component
   image version, chart `version` independent (Decision 5).
3. **Agent as a fourth lane:** confirmed (Decision 1 / 3).
4. **GHCR tag mutability:** immutable release tags + digest-pinned consumption
   confirmed as the intent for `#453` to verify (Decision 7).

### Rollout gate (decision is Accepted; rollout is staged)

The *decision* is ratified now. The *rollout* -- docs advertising install
commands and core removing its dormant operator/Helm CI -- is staged behind:

- [ ] `mcp-hangar-operator#26`: one verified operator image + manifest release,
      with a recorded digest.
- [ ] `helm-charts#7`: the three charts published to GHCR OCI, with recorded
      digests and a verified `helm pull`.
- [ ] Agent lane: `release.yml` authored in `mcp-hangar-agent`, first image
      released and verified.
- [ ] `#453`: compatibility matrix published with an owner, and GHCR security
      posture verified against the live registry.
- [ ] `docs`: the release hub advertises only the verified artifacts.

Like the dormant governance in ADR-008, the topology is *decided and asleep*
until these complete; nothing here claims it is operational today.

## Consequences

- **Independent cadence, at the cost of a matrix.** Each component ships when it
  is ready; a core patch does not gate an operator, agent, or chart release. The
  price is that "which versions work together" stops being obvious from a shared
  number and must be answered by the `#453` matrix -- a real maintenance
  obligation, not a formality.
- **The agent lane is a known gap, now on the record.** The `hangar-agent`
  chart already ships (`version`/`appVersion` `0.1.0`) but the agent image has
  no release workflow. Ratifying it as an independent lane makes authoring that
  workflow a tracked follow-up rather than an oversight discovered at first
  release.
- **The image/chart trigger asymmetry is intentional and guarded.** The
  `Chart.yaml` version-bump CI check (Decision 4) closes the one real hazard of
  the idempotent-push model -- a chart change that silently no-ops because its
  version was not bumped.
- **Dormant CI stays dormant a little longer.** Core keeps its operator/Helm CI
  until the rollout gate is met, because removing it before the independent
  lanes are proven would strand the fallback.
- **Docs can under-promise safely.** Because the index is gated on verified
  digests, a half-built topology cannot leak an install command that 404s or
  pulls a non-existent chart -- the failure mode the audit was worried about.
- **First release is a coordinated act, then never again.** Bootstrapping the
  first operator, agent, and chart releases needs a maintainer with GHCR write
  and org context; steady-state releases afterward are per-repo and independent.

## Alternatives Considered

- **Unified monorepo version (one tag releases everything).** Rejected: it
  re-couples exactly what the multi-repo split decoupled, forces a core patch to
  re-release the operator, agent, and charts, and makes "core `1.4.1` with
  operator `1.4.0`" unexpressible -- the normal, healthy state of independent
  components.
- **`docs` (or a hub repo) owns and orchestrates all releases centrally.**
  Rejected: it puts release authority in the repo furthest from each artifact's
  build, and turns docs -- a *consumer* of verified digests -- into the
  *producer*, inverting the trust direction and coupling doc edits to artifact
  publication.
- **Force every lane onto one identical trigger.** Rejected: a binary image and
  a text chart have genuinely different release semantics; imposing one
  mechanism on both trades a real fit for a cosmetic symmetry. The asymmetry is
  ratified explicitly (Decision 4) and made safe with the version-bump guard,
  rather than eliminated.

## References

- Parent / ratification: `mcp-hangar/mcp-hangar#410` (proposed ADR-009),
  `mcp-hangar/docs#22` (this document).
- Follow-ups: `mcp-hangar-operator#26` (first image/manifest release),
  `mcp-hangar/helm-charts#7` (OCI chart policy + first release),
  `mcp-hangar/mcp-hangar#453` (compatibility matrix + GHCR security policy),
  agent-lane `release.yml` (to be filed against `mcp-hangar-agent`).
- Related: ADR-004 (digest pinning; the trust unit for released artifacts),
  ADR-008 (do-not-advertise-what-does-not-run, and decided-but-dormant framing).
- Cleanup context: `mcp-hangar/mcp-hangar#466` (remove vestigial `packages/core/`).
- Workflows audited (2026-07-14): `mcp-hangar-operator/.github/workflows/release.yml`,
  `helm-charts/.github/workflows/release.yml`, `docs/.github/workflows/publish.yml`;
  `mcp-hangar-agent` has no release workflow.
