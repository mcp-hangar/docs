# Release Compatibility & Artifact Security Policy

MCP Hangar ships as independently versioned artifacts (see
[Releases & Artifacts](../getting-started/releases.md) for where each one lives
and how to install it). Because they release on separate SemVer lines per
[ADR-009](../adr/ADR-009-independent-release-topology.md), "which versions work
together" is answered by the compatibility matrix below, not by a shared
version number. This page is that matrix plus the artifact-security policy that
governs how the images and charts are published and verified.

> **Status: draft policy, rollout pending.**
> A live audit (2026-07-14) found releases only on the Python core lane; the
> operator image, agent image, and Helm charts have not yet cut a first
> release. The *policy* below is ratified as the target; the **Verification
> status** section tracks what must be proven before independent releases are
> declared supported. This mirrors ADR-009's "decided and asleep" framing —
> nothing here claims the topology is operational today.

## Ownership and update procedure

- **Owner:** the release maintainers (the `#453` / ADR-009 owners). The matrix
  has a single named owner recorded in the repository `CODEOWNERS` for this
  file; changes require that owner's review.
- **Update trigger:** every artifact release updates this matrix in the same
  PR, or in an immediate follow-up PR, that cuts the release. A release whose
  compatibility is not reflected here is incomplete.
- **Cadence:** the matrix is reviewed at least once per core minor release even
  if satellites did not move, to re-confirm the Kubernetes support window.

## Compatibility matrix

Each row is a supported *combination*. An artifact version absent from this
table is **not** a supported combination — it may work, but it is not covered.

| Core (`mcp-hangar`) | Operator image | Agent image | Helm charts | Kubernetes |
| --- | --- | --- | --- | --- |
| `1.4.x` | *(unreleased)* | *(unreleased)* | *(unreleased)* | — |

Rules for reading and extending the matrix:

- **Core** is the reference axis: it is the only lane with published releases
  today (`v1.4.0`). Every supported combination pins a concrete core minor.
- **Operator / Agent / Helm** columns are filled with the first verified
  release digests as `mcp-hangar-operator#26`, `mcp-hangar-agent#30`, and
  `helm-charts#7` land. Until then they read `(unreleased)` and no combination
  involving them is supported.
- **Kubernetes** records the tested server range for combinations that include
  the operator or a chart; it is left `—` while those lanes are unreleased.
- **SemVer boundaries:** a change that breaks a documented combination is a
  MAJOR bump of the artifact that changed. Adding a newly-tested combination is
  a MINOR/docs change to this matrix, not a version bump of any artifact.

## CRD upgrade and rollback policy

The operator owns the CRDs; this policy binds the operator lane.

- **Additive within a major.** New CRD fields are optional with safe defaults
  and are introduced in a MINOR operator release. Existing objects remain valid
  without edits.
- **Breaking changes require a new CRD version + conversion.** A field removal,
  a type change, or a semantics change ships under a new CRD API version
  (`v1alpha2`, `v1beta1`, …) with a conversion path (webhook or a documented
  manual migration). The old version is served for at least one operator MINOR
  before it is deprecated, and deprecation is announced in the release notes.
- **Rollback constraint.** Downgrading the operator is supported only within the
  same served CRD version. Rolling back across a CRD-version bump requires the
  documented conversion in reverse and is not guaranteed lossless — objects
  created with new-version-only fields may not round-trip. Each operator release
  states its safe rollback floor.
- **Stored version.** Only one CRD version is marked `storage: true` at a time;
  bumping it is itself a breaking change subject to the rule above.

## Artifact security policy (GHCR)

All images and charts publish to the org GHCR namespace
(`ghcr.io/mcp-hangar/…`). The following posture is the target for `#453`
verification against the live registry.

| Property | Policy |
| --- | --- |
| **Visibility** | Public. Anonymous `docker pull` / `helm pull` with no auth. |
| **Ownership** | Owned by the `mcp-hangar` org, not a personal account. |
| **Writers** | Only the per-repo release workflows (via the scoped release token); no interactive human pushes to release tags. |
| **Retention** | Release tags are kept indefinitely. Untagged / build-cache layers are eligible for GC; no released digest is ever pruned. |
| **Tag mutability** | Release tags (`X.Y.Z`, `X.Y`) are **immutable** once published — never re-pointed. `latest` is a mutable convenience alias only, never a trust anchor. |
| **Provenance / SBOM** | Each image ships build provenance and an SBOM attestation attached to its digest. |
| **Signing** | Images and charts are signed with keyless (OIDC) `cosign`; the signing identity is the publishing workflow. |
| **Digest pinning** | Consumers pin by digest (`@sha256:…`), per [ADR-004](../adr/ADR-004-sep-1766-digest-pinning.md). Tags are for discovery; digests are the unit of trust. |

### Consumer verification

Pull by digest and verify the signature before deploying:

```bash
# Resolve a tag to an immutable digest, then pin it.
docker buildx imagetools inspect ghcr.io/mcp-hangar/mcp-hangar-operator:<version>

# Verify the keyless signature (identity = the publishing workflow).
cosign verify ghcr.io/mcp-hangar/mcp-hangar-operator@sha256:<digest> \
  --certificate-identity-regexp 'https://github.com/mcp-hangar/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Charts are verified the same way against
`oci://ghcr.io/mcp-hangar/charts/<chart>`.

## Verification status

The policy above is declared *supported* only when every box is checked. These
are the human- and rollout-gated acceptance criteria from `#453`; they stay
unchecked until the first releases land and the owners sign off.

- [ ] Matrix has a named owner in `CODEOWNERS` and the update procedure is in
      effect.
- [ ] First operator image + manifest released with a verified digest and
      install instructions (`mcp-hangar-operator#26`).
- [ ] First charts published with verified digests and a verified `helm pull`
      (`helm-charts#7`).
- [ ] Agent image release lane authored and first image released
      (`mcp-hangar-agent#30`).
- [ ] CRD rollback / compatibility limits validated against a real operator
      release.
- [ ] GHCR posture (visibility, immutability, signing, SBOM/provenance,
      retention) verified against the live registry.
- [ ] Security policy approved by the release and security owners.

## References

- [ADR-009 — Independent Release Topology](../adr/ADR-009-independent-release-topology.md)
- [ADR-004 — Digest Pinning](../adr/ADR-004-sep-1766-digest-pinning.md)
- [Releases & Artifacts](../getting-started/releases.md)
- [Release Operations Runbook](../runbooks/RELEASE.md)
- Tracking issue: [mcp-hangar/mcp-hangar#453](https://github.com/mcp-hangar/mcp-hangar/issues/453);
  parent [#410](https://github.com/mcp-hangar/mcp-hangar/issues/410).
