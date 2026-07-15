# Release Compatibility & Artifact Security Policy

MCP Hangar ships as independently versioned artifacts (see
[Releases & Artifacts](../getting-started/releases.md) for where each one lives
and how to install it). Because they release on separate SemVer lines per
[ADR-009](../adr/ADR-009-independent-release-topology.md), "which versions work
together" is answered by the compatibility matrix below, not by a shared
version number. This page is that matrix plus the artifact-security policy that
governs how the images and charts are published and verified.

> **Status: partial rollout — operator and agent images released; charts and
> sign-off pending.**
> As of 2026-07-15 the operator image (`v0.12.0`) and the agent image
> (`v0.1.0`) are published, public, and verified by digest (see *Released
> artifacts*); the Helm charts have not yet cut a first release. Independent
> release is **not yet declared supported**: the **Verification status** section
> still has open, human-gated items — notably that the release workflows do
> **not yet sign images or attach SBOM/provenance**, so the `cosign verify`
> recipe below does not succeed against today's images.

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
| `1.4.x` | `0.12.0` | `0.1.0` | *(unreleased)* | — |

Rules for reading and extending the matrix:

- **Core** is the reference axis: every supported combination pins a concrete
  core minor (`v1.4.0` is the current published core).
- **Operator / Agent / Helm** columns carry the released version; the verified
  digests are in *Released artifacts* below. Operator (`mcp-hangar-operator#26`)
  and agent (`mcp-hangar-agent#30`) have landed; the Helm column stays
  `(unreleased)` until `helm-charts#7`, so this row is **not yet a fully
  supported combination** — it also awaits Kubernetes range validation and
  sign-off (see Verification status).
- **Kubernetes** records the tested server range for combinations that include
  the operator or a chart; it is left `—` until that range is validated against
  a real operator install.
- **SemVer boundaries:** a change that breaks a documented combination is a
  MAJOR bump of the artifact that changed. Adding a newly-tested combination is
  a MINOR/docs change to this matrix, not a version bump of any artifact.

### Released artifacts (verified)

Pinned digests for the published images, confirmed by anonymous pull on
2026-07-15. Charts are added when `helm-charts#7` lands.

| Artifact | Version | Digest | Visibility |
| --- | --- | --- | --- |
| Operator image (`ghcr.io/mcp-hangar/mcp-hangar-operator`) | `0.12.0` | `sha256:445148d02e6ccd68253f5a14c65b879dbe2cb91b01561f78b1c0a204a468a523` | Public |
| Agent image (`ghcr.io/mcp-hangar/hangar-agent`) | `0.1.0` | `sha256:768072be16b181162276907eada2ff17bb0f22b3b37c030ab5be9a848a19e3fe` | Public |

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

> **Not yet active (2026-07-15):** the operator and agent release workflows
> currently build and push images but do **not** sign them or attach
> SBOM/provenance, so `cosign verify` fails against today's images. Wiring
> keyless signing + SBOM into the release workflows is a tracked follow-up and a
> prerequisite for checking the GHCR-posture box below. Until then, pin by digest
> from *Released artifacts* and treat the signature step as pending.

## Verification status

The policy above is declared *supported* only when every box is checked. The
image lanes have landed; the remaining boxes are the human- and rollout-gated
criteria from `#453` (charts, image signing, validation, and owner sign-off).

- [ ] Matrix has a named owner in `CODEOWNERS` and the update procedure is in
      effect.
- [x] First operator image + manifest released with a verified digest and
      install instructions (`mcp-hangar-operator#26`) — `0.12.0`, public,
      `sha256:445148d0…a468a523`, `install.yaml` attached to the release.
- [ ] First charts published with verified digests and a verified `helm pull`
      (`helm-charts#7`).
- [x] Agent image release lane authored and first image released
      (`mcp-hangar-agent#30`) — `0.1.0`, public, `sha256:768072be…a19e3fe`.
- [ ] CRD rollback / compatibility limits validated against a real operator
      release.
- [ ] GHCR posture (visibility, immutability, signing, SBOM/provenance,
      retention) verified against the live registry. Visibility is confirmed
      public for both images; **signing and SBOM/provenance are not yet
      implemented** in the release workflows (tracked follow-up).
- [ ] Security policy approved by the release and security owners.

## References

- [ADR-009 — Independent Release Topology](../adr/ADR-009-independent-release-topology.md)
- [ADR-004 — Digest Pinning](../adr/ADR-004-sep-1766-digest-pinning.md)
- [Releases & Artifacts](../getting-started/releases.md)
- [Release Operations Runbook](../runbooks/RELEASE.md)
- Tracking issue: [mcp-hangar/mcp-hangar#453](https://github.com/mcp-hangar/mcp-hangar/issues/453);
  parent [#410](https://github.com/mcp-hangar/mcp-hangar/issues/410).
