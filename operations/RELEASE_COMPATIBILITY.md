# Release Compatibility & Artifact Security Policy

MCP Hangar ships as independently versioned artifacts (see
[Releases & Artifacts](../getting-started/releases.md) for where each one lives
and how to install it). Because they release on separate SemVer lines per
[ADR-009](../adr/ADR-009-independent-release-topology.md), "which versions work
together" is answered by the compatibility matrix below, not by a shared
version number. This page is that matrix plus the artifact-security policy that
governs how the images and charts are published and verified.

> **Status: released and signed; the published charts carry their fixes — but
> chart tags are mutable, which is a release-integrity bug
> (`mcp-hangar/helm-charts#36`).**
> As of 2026-07-16 every lane has a published, public, **cosign-signed**,
> digest-verified artifact with SBOM/provenance (see *Released artifacts*): core
> image `1.5.1`, operator `0.12.2`, and both Helm charts.
> Image signing + SBOM (`mcp-hangar/mcp-hangar#467`) is done.
>
> Live cluster testing found defects that made a default `helm install` fail
> outright — a config key the 1.5 server rejects, flags the operator image does
> not accept, CRDs that do not match the kinds the image watches, and a CRD the
> API server refuses. Those are **fixed, and the fixes are present in the
> currently-published charts**: verified by pulling `charts/mcp-hangar 0.13.3` and
> `charts/mcp-hangar-operator 0.12.1` from GHCR and inspecting their contents, not
> by inference. The `helm-charts` repo also had no chart lint/render/install CI at
> all — that gate now exists, which is why this class of defect will not ship
> again.
>
> **The fixes reached the registry the wrong way.** `release-charts` re-pushes an
> already-published version on every merge to `main`, so a released tag's content
> changes over time (`mcp-hangar/helm-charts#36`): `mcp-hangar-operator 0.12.1`
> today is not the `0.12.1` published before those fixes landed. That contradicts
> the tag-immutability rule in the *Artifact security policy* below, and it is why
> the digests recorded in *Released artifacts* drift. Until #36 lands, treat those
> digests as a **snapshot, not a pin**, and expect a chart tag to move under you.
>
> Kubernetes-range validation is **done** (see the matrix). Independent release
> is still **not formally declared supported**: the remaining **Verification
> status** items are human-gated — a named `CODEOWNERS` owner and security/owner
> sign-off — plus the mutable-tag fix.

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

| Core (`mcp-hangar`) | Operator image | Helm charts (core / operator) | Kubernetes |
| --- | --- | --- | --- |
| `1.5.x` | `0.12.2` | `0.13.3` / `0.12.1` | `1.25` -- `1.36` |

Rules for reading and extending the matrix:

- **Core** is the reference axis: every supported combination pins a concrete
  core minor (`v1.5.1` is the current published core).
- **Operator / Helm** columns carry the released version; the verified
  digests are in *Released artifacts* below. Both lanes have landed
  (`mcp-hangar-operator#26`, `helm-charts#7`) and the
  Kubernetes range is now validated. The row is still **not formally a supported
  combination** until the owners sign off and chart releases become immutable
  (see Verification status).
- **Kubernetes** records the tested server range for combinations that include
  the operator or a chart. The declared `>=1.25` floor is **test-confirmed**: on a
  real **v1.25.16** control plane both charts install, the operator's CRDs reach
  `Established`, an `MCPServer` reconciles into a child resource with correct
  owner references, and the core gateway serves `/health/ready` 200. The same
  charts run on **v1.36.1**. Every apiVersion the charts render (`autoscaling/v2`,
  `policy/v1`, `networking.k8s.io/v1`, `admissionregistration.k8s.io/v1`,
  `apiextensions.k8s.io/v1`) has been GA since v1.16--v1.23, so nothing in them is
  version-fragile inside that window. Validated against the charts on `helm-charts`
  `main`, whose content is what the published tags currently serve (see *Status*
  and `mcp-hangar/helm-charts#36`).
- **SemVer boundaries:** a change that breaks a documented combination is a
  MAJOR bump of the artifact that changed. Adding a newly-tested combination is
  a MINOR/docs change to this matrix, not a version bump of any artifact.

### Released artifacts (verified)

Digests for every published artifact, confirmed by anonymous pull. All are
public; images and charts marked *signed* carry a keyless cosign signature and an
SBOM/provenance attestation.

**Image digests are pins. Chart digests are not** -- `release-charts` re-pushes an
existing chart version on every merge to `main`, so a chart tag's digest moves
(`mcp-hangar/helm-charts#36`). The chart digests below were read on 2026-07-16 and
will drift again on the next merge; the image digests (2026-07-15) are stable.

| Artifact | Version | Digest | Signed |
| --- | --- | --- | --- |
| Core image (`ghcr.io/mcp-hangar/mcp-hangar`) | `1.5.1` | `sha256:a2d6ed0fe32b04b6cd248df33f9e89b88a88b242e5a8d46a670adf766dc180f4` | ✅ |
| Operator image (`ghcr.io/mcp-hangar/mcp-hangar-operator`) | `0.12.2` | `sha256:91f8fea38adc02f84ed2c77b6efbeab38363616f088b03baf7d2eee5c34ce42f` | ✅ |
| Chart `charts/mcp-hangar` (appVersion `1.5.1`) | `0.13.3` | `sha256:6c0130f1f79e24e9b0f21b5f87c21faefce66bcfcb08a5de99cf53a356294f22` | ✅ |
| Chart `charts/mcp-hangar-operator` (appVersion `0.12.2`) | `0.12.1` | `sha256:fa73756b590c26478ab93ad15fe218dd5bf168a52e0bfe66faf697aa8a127702` | ✅ |

Superseded (do not use): operator image `0.12.0`/`0.12.1`
(unsigned), and the `mcp-hangar` chart `0.12.0`/`0.13.0`/`0.13.1` (the `0.12.0`
chart pointed at a non-existent core image tag; `0.13.1` predates the install
fixes and still declares `appVersion 1.4.0`). The core image is versioned on its
own `1.x` line (matching PyPI core); its release workflow already cosign-signs
and attaches build provenance.

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

> **Active (2026-07-15):** every release workflow signs keyless with cosign and
> attaches SBOM/provenance — the operator and chart lanes
> (`mcp-hangar/mcp-hangar#467`) and the core image lane (which already signed and
> attached provenance) — so the recipe above succeeds against every artifact in
> *Released artifacts*.

## Verification status

The policy above is declared *supported* only when every box is checked. All
release lanes are published and signed and the Kubernetes range is now
validated; the remaining boxes are the human-gated criteria from `#453` (a named
owner and security sign-off) plus a chart re-release.

- [ ] Matrix has a named owner in `CODEOWNERS` and the update procedure is in
      effect.
- [x] First operator image + manifest released with a verified digest and
      install instructions (`mcp-hangar-operator#26`) — signed `0.12.2`, public,
      `sha256:91f8fea3…c34ce42f`, `install.yaml` attached to the release.
- [x] First charts published with verified digests (`helm-charts#7`) — both
      charts public and signed: `mcp-hangar 0.13.1`, `mcp-hangar-operator 0.12.1`
      (digests in *Released artifacts*). The current core
      chart is `0.13.3`; `0.13.1` predates the install fixes and is superseded.
- [x] The published charts install: the fixes found by live testing are present
      in `charts/mcp-hangar 0.13.3` and `charts/mcp-hangar-operator 0.12.1` as
      served today (verified by pulling and inspecting them).
- [ ] **Chart releases are immutable** — `release-charts` currently re-pushes an
      existing version on every merge to `main`, so a released tag's content
      changes over time (`mcp-hangar/helm-charts#36`). Until this is fixed, no
      chart tag or digest here is a stable pin.
- [x] Kubernetes support range validated (`1.25` -- `1.36`) against a real
      control plane at the declared floor `v1.25.16` and at `v1.36.1`: charts
      install, CRDs reach `Established`, an `MCPServer` reconciles into a child
      with correct owner references, and the gateway serves `/health/ready` 200.
      Validated against the fixed charts on `main`.
- *(Agent image release lane retired along with the discontinued cluster
  agent product; it never reached general availability and is no longer
  part of this matrix or the verification checklist.)*
- [x] GHCR signing + SBOM/provenance (`mcp-hangar/mcp-hangar#467`) — the core
      image, operator, and all charts carry a keyless cosign signature +
      attestation, confirmed present in the registry; public visibility confirmed
      for all artifacts. (Immutability/retention follow GHCR defaults.)
- [ ] CRD rollback / compatibility limits validated against a real operator
      release.
- [ ] Security policy approved by the release and security owners.

## References

- [ADR-009 — Independent Release Topology](../adr/ADR-009-independent-release-topology.md)
- [ADR-004 — Digest Pinning](../adr/ADR-004-sep-1766-digest-pinning.md)
- [Releases & Artifacts](../getting-started/releases.md)
- [Release Operations Runbook](../runbooks/RELEASE.md)
- Tracking issue: [mcp-hangar/mcp-hangar#453](https://github.com/mcp-hangar/mcp-hangar/issues/453);
  parent [#410](https://github.com/mcp-hangar/mcp-hangar/issues/410).
