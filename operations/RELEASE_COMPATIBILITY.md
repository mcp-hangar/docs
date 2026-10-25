# Release Compatibility & Artifact Security Policy

MCP Hangar ships as independently versioned artifacts (see
[Releases & Artifacts](../getting-started/releases.md) for where each one lives
and how to install it). Because they release on separate SemVer lines per
[ADR-009](../adr/ADR-009-independent-release-topology.md), "which versions work
together" is answered by the compatibility matrix below, not by a shared
version number. This page is that matrix plus the artifact-security policy that
governs how the images and charts are published and verified.

> **Status: released, signed, and pinned — the published charts carry their
> fixes and chart tags are now immutable (`mcp-hangar/helm-charts#36`, closed;
> fixed by the fail-safe publish guard #37).**
> Since 2026-08-09 every lane — core image, operator image, and both Helm
> charts — has a published, public, **cosign-signed**, digest-verified artifact
> with SBOM/provenance. Which versions those are is not restated here: read
> *Released artifacts* below, which is regenerated from the registry. The `2.x`
> line went stable on 2026-07-31; it was previously excluded from this page as a
> release candidate, which the page kept asserting after it stopped being true.
> Image signing + SBOM (`mcp-hangar/mcp-hangar#467`) is done.
>
> Live cluster testing found defects that made a default `helm install` fail
> outright — a config key the 1.5 server rejects, flags the operator image does
> not accept, CRDs that do not match the kinds the image watches, and a CRD the
> API server refuses. Those are **fixed, and every chart published since carries
> the fixes**: first verified by pulling `charts/mcp-hangar 0.13.4` and
> `charts/mcp-hangar-operator 0.12.3` — the published charts at that time — from
> GHCR and inspecting their contents, not by inference. Every chart published
> since descends from those; the current ones are in *Released artifacts*.
> The `helm-charts` repo also had no chart lint/render/install CI at
> all — that gate now exists, which is why this class of defect will not ship
> again.
>
> **Chart tags are immutable (`mcp-hangar/helm-charts#36`, closed).** The publish
> guard probes with `crane manifest` and skips any version already in the registry
> (#37), so a released chart tag's content never changes after publication — the
> digests recorded in *Released artifacts* are stable pins.
>
> Kubernetes-range validation is **done** (see the matrix). Independent release
> is still **not formally declared supported**: the remaining **Verification
> status** items are human-gated — a named `CODEOWNERS` owner and security/owner
> sign-off.

## Ownership and update procedure

- **Owner:** the release maintainers (the `#453` / ADR-009 owners). The matrix
  has a single named owner recorded in the repository `CODEOWNERS` for this
  file; changes require that owner's review.
- **Update trigger:** *Released artifacts* is regenerated from the registry by
  the `sync-release-matrix` workflow — daily, or on demand right after a release.
  The **compatibility matrix** above it is a human judgement about supported
  combinations and is not generated: a release adds its row in the PR that cuts
  it, or in an immediate follow-up. A release whose compatibility is not
  reflected here is incomplete, and nothing automated will notice.
- **Cadence:** the matrix is reviewed at least once per core minor release even
  if satellites did not move, to re-confirm the Kubernetes support window.

## Compatibility matrix

Each row is a supported *combination*. An artifact version absent from this
table is **not** a supported combination — it may work, but it is not covered.

| Core (`mcp-hangar`) | Operator image | Helm charts (core / operator) | Kubernetes |
| --- | --- | --- | --- |
| `2.21.x` | `0.17.2` | `0.15.25` / `0.12.15` | `1.25` -- `1.36` |
| `2.20.x` | `0.17.1` | `0.15.21` / `0.12.13` | `1.25` -- `1.36` |
| `2.19.x` | `0.17.1` | `0.15.20` / `0.12.13` | `1.25` -- `1.36` |
| `2.18.x` | `0.17.1` | `0.15.16` / `0.12.13` | `1.25` -- `1.36` |
| `2.17.x` | `0.17.1` | `0.15.14` / `0.12.13` | `1.25` -- `1.36` |
| `2.16.x` | `0.17.1` | `0.15.12` / `0.12.13` | `1.25` -- `1.36` |
| `2.15.x` | `0.17.1` | `0.15.11` / `0.12.13` | `1.25` -- `1.36` |
| `2.14.x` | `0.17.1` | `0.15.10` / `0.12.13` | `1.25` -- `1.36` |
| `2.13.x` | `0.16.0` | `0.15.8` / `0.12.11` | `1.25` -- `1.36` |
| `2.12.x` | `0.16.0` | `0.15.6` / `0.12.11` | `1.25` -- `1.36` |
| `2.11.x` | `0.16.0` | `0.15.5` / `0.12.11` | `1.25` -- `1.36` |
| `2.10.x` | `0.15.2` | `0.15.4` / `0.12.8` | `1.25` -- `1.36` |
| `2.9.x` | `0.15.2` | `0.15.2` / `0.12.8` | `1.25` -- `1.36` |
| `2.8.x` | `0.15.2` | `0.15.1` / `0.12.8` | `1.25` -- `1.36` |
| `2.7.x` | `0.15.2` | `0.15.0` / `0.12.7` | `1.25` -- `1.36` |
| `2.6.x` | `0.15.2` | `0.14.4` / `0.12.7` | `1.25` -- `1.36` |
| `2.5.x` | `0.15.0` | `0.14.1` / `0.12.5` | `1.25` -- `1.36` |
| `2.0.x` | `0.15.0` | `0.13.7` / `0.12.5` | `1.25` -- `1.36` |
| `1.6.x` | `0.15.0` | `0.13.6` / `0.12.5` | `1.25` -- `1.36` |

**Rows for cores newer than `2.21.x` are not in this table yet.** The *Chart
release history* below lists every published chart with the core it carries, and
is regenerated from the registry. Until the owners add rows here, those cores are
not a supported combination under the rule above.

Each chart in the table carries the matching core as its `appVersion`, and
`image.tag` defaults to `appVersion`, so a plain `helm install` of a chart pulls
the core on its row: `0.15.25` carries `2.21.2`, `0.15.21` carries `2.20.0`,
`0.15.20` carries `2.19.1`, `0.15.16` carries `2.18.1`, `0.15.14` carries `2.17.1`,
`0.15.12` carries `2.16.0`, `0.15.11` carries `2.15.0`, `0.15.10` carries
`2.14.1`, `0.15.8` carries `2.13.1`, `0.15.6` carries `2.12.0`, `0.15.5` carries
`2.11.0`, `0.15.4` carries `2.10.1`, `0.15.2` carries `2.9.0`, `0.15.1` carries
`2.8.0`, `0.15.0` carries `2.7.0`, `0.14.4` carries `2.6.0`, `0.14.1` carries
`2.5.0`. A row names the newest chart carrying that core minor, so the patch it
pulls is that minor's latest. The newest chart's `appVersion` is
what the generated *Released artifacts* table below reads back out of the
registry. Older charts stay on their own lines: `0.13.7` carries
`appVersion: 2.0.0` and `0.13.6` carries `appVersion: 1.6.2`. Charts before
`0.13.6` each carry whichever core they shipped against at the time (down to
`1.4.0` on `0.13.1`), so they are not a way onto the `1.6.x` row. Pin the chart
version, not just the image tag, if you are staying on an older line.

Rules for reading and extending the matrix:

- **Core** is the reference axis: every supported combination pins a concrete
  core minor. The current published core is in *Released artifacts*, not named
  here. `1.6.x` is closed and receives no fixes, including the
  approval-authorization fix released in 2.0.0.
- **Operator / Helm** columns carry the released version; the verified
  digests are in *Released artifacts* below. Both lanes have landed
  (`mcp-hangar-operator#26`, `helm-charts#7`) and the
  Kubernetes range is now validated. The row is still **not formally a supported
  combination** until the owners sign off (see Verification status).
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

**Image and chart digests are pins.** The publish guard (`mcp-hangar/helm-charts#37`)
skips re-push of any already-published version, so a released tag's digest is
stable — verified de-facto: the earlier-recorded `0.13.2` chart digest is
unchanged today. Read once, pin by digest.

<!-- BEGIN generated: released-artifacts — regenerated by scripts/gen-artifact-matrix.sh (sync-release-matrix workflow) from the GHCR registry. Do not hand-edit. -->
| Artifact | Version | Digest | Signed |
| --- | --- | --- | --- |
| Core image (`ghcr.io/mcp-hangar/mcp-hangar`) | `2.34.3` | `sha256:d0817457b97f8f95f2fdad901bb9d177c85b8c586d847181f9ee20d4054278bf` | ✅ |
| Operator image (`ghcr.io/mcp-hangar/mcp-hangar-operator`) | `0.17.35` | `sha256:10890b1c3b576701c4b6c4a0bb9ea2909876ce1128cf0673b54760d41747d9b8` | ✅ |
| Chart `charts/mcp-hangar` (appVersion `2.34.3`) | `0.15.47` | `sha256:f1604aaa960c765f981b8bfbe6ba1c19d5b420b3fe13f5d0ab0e464d9ee5d8b9` | ✅ |
| Chart `charts/mcp-hangar-operator` (appVersion `0.17.35`) | `0.12.51` | `sha256:170971c96478f3d0f0d7afa20e4dfb222ddfb58382278de12fd6d1c466693493` | ✅ |
<!-- END generated: released-artifacts -->

### Chart release history

Every published chart version with the core or operator it carries as
`appVersion` and the Kubernetes range it declares. This is the complete list;
the compatibility matrix above names only the newest chart per core minor.

<!-- BEGIN generated: chart-release-history — regenerated by scripts/gen-artifact-matrix.sh (sync-release-matrix workflow) from the GHCR registry. Do not hand-edit. -->
**Chart `charts/mcp-hangar`**

| Chart version | appVersion | kubeVersion |
| --- | --- | --- |
| `0.15.47` | `2.34.3` | `>=1.25.0-0` |
| `0.15.46` | `2.34.2` | `>=1.25.0-0` |
| `0.15.45` | `2.34.1` | `>=1.25.0-0` |
| `0.15.44` | `2.34.0` | `>=1.25.0-0` |
| `0.15.43` | `2.33.0` | `>=1.25.0-0` |
| `0.15.42` | `2.32.1` | `>=1.25.0-0` |
| `0.15.41` | `2.32.0` | `>=1.25.0-0` |
| `0.15.40` | `2.31.0` | `>=1.25.0-0` |
| `0.15.39` | `2.30.0` | `>=1.25.0-0` |
| `0.15.38` | `2.29.0` | `>=1.25.0-0` |
| `0.15.37` | `2.28.0` | `>=1.25.0-0` |
| `0.15.36` | `2.27.5` | `>=1.25.0-0` |
| `0.15.35` | `2.27.4` | `>=1.25.0-0` |
| `0.15.34` | `2.27.2` | `>=1.25.0-0` |
| `0.15.33` | `2.27.0` | `>=1.25.0-0` |
| `0.15.32` | `2.26.0` | `>=1.25.0-0` |
| `0.15.31` | `2.25.0` | `>=1.25.0-0` |
| `0.15.30` | `2.25.0` | `>=1.25.0-0` |
| `0.15.29` | `2.24.0` | `>=1.25.0-0` |
| `0.15.28` | `2.23.0` | `>=1.25.0-0` |
| `0.15.27` | `2.22.1` | `>=1.25.0-0` |
| `0.15.26` | `2.22.0` | `>=1.25.0-0` |
| `0.15.25` | `2.21.2` | `>=1.25.0-0` |
| `0.15.24` | `2.21.1` | `>=1.25.0-0` |
| `0.15.23` | `2.21.1` | `>=1.25.0-0` |
| `0.15.22` | `2.21.0` | `>=1.25.0-0` |
| `0.15.21` | `2.20.0` | `>=1.25.0-0` |
| `0.15.20` | `2.19.1` | `>=1.25.0-0` |
| `0.15.19` | `2.19.0` | `>=1.25.0-0` |
| `0.15.18` | `2.18.2` | `>=1.25.0-0` |
| `0.15.17` | `2.18.2` | `>=1.25.0-0` |
| `0.15.16` | `2.18.1` | `>=1.25.0-0` |
| `0.15.15` | `2.18.0` | `>=1.25.0-0` |
| `0.15.14` | `2.17.1` | `>=1.25.0-0` |
| `0.15.13` | `2.17.0` | `>=1.25.0-0` |
| `0.15.12` | `2.16.0` | `>=1.25.0-0` |
| `0.15.11` | `2.15.0` | `>=1.25.0-0` |
| `0.15.10` | `2.14.1` | `>=1.25.0-0` |
| `0.15.9` | `2.14.0` | `>=1.25.0-0` |
| `0.15.8` | `2.13.1` | `>=1.25.0-0` |
| `0.15.7` | `2.13.0` | `>=1.25.0-0` |
| `0.15.6` | `2.12.0` | `>=1.25.0-0` |
| `0.15.5` | `2.11.0` | `>=1.25.0-0` |
| `0.15.4` | `2.10.1` | `>=1.25.0-0` |
| `0.15.3` | `2.10.0` | `>=1.25.0-0` |
| `0.15.2` | `2.9.0` | `>=1.25.0-0` |
| `0.15.1` | `2.8.0` | `>=1.25.0-0` |
| `0.15.0` | `2.7.0` | `>=1.25.0-0` |
| `0.14.4` | `2.6.0` | `>=1.25.0-0` |
| `0.14.3` | `2.5.3` | `>=1.25.0-0` |
| `0.14.2` | `2.5.2` | `>=1.25.0-0` |
| `0.14.1` | `2.5.0` | `>=1.25.0-0` |
| `0.14.0` | `2.4.0` | `>=1.25.0-0` |
| `0.13.11` | `2.4.0` | `>=1.25.0-0` |
| `0.13.10` | `2.3.0` | `>=1.25.0-0` |
| `0.13.9` | `2.2.1` | `>=1.25.0-0` |
| `0.13.8` | `2.2.0` | `>=1.25.0-0` |
| `0.13.7` | `2.0.0` | `>=1.25.0-0` |
| `0.13.6` | `1.6.2` | `>=1.25.0-0` |
| `0.13.5` | `1.6.1` | `>=1.25.0-0` |
| `0.13.4` | `1.6.0` | `>=1.25.0-0` |
| `0.13.3` | `1.5.1` | `>=1.25.0-0` |
| `0.13.2` | `1.5.0` | `>=1.25.0-0` |
| `0.13.1` | `1.4.0` | `>=1.25.0-0` |
| `0.13.0` | `1.4.0` | `>=1.25.0-0` |
| `0.12.0` | `0.12.0` | `>=1.25.0-0` |

**Chart `charts/mcp-hangar-operator`**

| Chart version | appVersion | kubeVersion |
| --- | --- | --- |
| `0.12.51` | `0.17.35` | `>=1.30.0-0` |
| `0.12.50` | `0.17.34` | `>=1.30.0-0` |
| `0.12.49` | `0.17.33` | `>=1.30.0-0` |
| `0.12.48` | `0.17.32` | `>=1.30.0-0` |
| `0.12.47` | `0.17.29` | `>=1.30.0-0` |
| `0.12.46` | `0.17.29` | `>=1.30.0-0` |
| `0.12.45` | `0.17.28` | `>=1.30.0-0` |
| `0.12.44` | `0.17.28` | `>=1.30.0-0` |
| `0.12.43` | `0.17.27` | `>=1.30.0-0` |
| `0.12.42` | `0.17.26` | `>=1.30.0-0` |
| `0.12.41` | `0.17.25` | `>=1.30.0-0` |
| `0.12.40` | `0.17.24` | `>=1.30.0-0` |
| `0.12.39` | `0.17.23` | `>=1.30.0-0` |
| `0.12.38` | `0.17.22` | `>=1.30.0-0` |
| `0.12.37` | `0.17.21` | `>=1.30.0-0` |
| `0.12.36` | `0.17.20` | `>=1.30.0-0` |
| `0.12.35` | `0.17.19` | `>=1.30.0-0` |
| `0.12.34` | `0.17.18` | `>=1.25.0-0` |
| `0.12.33` | `0.17.17` | `>=1.25.0-0` |
| `0.12.32` | `0.17.17` | `>=1.25.0-0` |
| `0.12.31` | `0.17.16` | `>=1.25.0-0` |
| `0.12.30` | `0.17.15` | `>=1.25.0-0` |
| `0.12.29` | `0.17.14` | `>=1.25.0-0` |
| `0.12.28` | `0.17.13` | `>=1.25.0-0` |
| `0.12.27` | `0.17.12` | `>=1.25.0-0` |
| `0.12.26` | `0.17.10` | `>=1.25.0-0` |
| `0.12.25` | `0.17.9` | `>=1.25.0-0` |
| `0.12.24` | `0.17.8` | `>=1.25.0-0` |
| `0.12.23` | `0.17.8` | `>=1.25.0-0` |
| `0.12.22` | `0.17.7` | `>=1.25.0-0` |
| `0.12.21` | `0.17.6` | `>=1.25.0-0` |
| `0.12.20` | `0.17.6` | `>=1.25.0-0` |
| `0.12.19` | `0.17.5` | `>=1.25.0-0` |
| `0.12.18` | `0.17.5` | `>=1.25.0-0` |
| `0.12.17` | `0.17.4` | `>=1.25.0-0` |
| `0.12.16` | `0.17.3` | `>=1.25.0-0` |
| `0.12.15` | `0.17.2` | `>=1.25.0-0` |
| `0.12.14` | `0.17.2` | `>=1.25.0-0` |
| `0.12.13` | `0.17.1` | `>=1.25.0-0` |
| `0.12.12` | `0.17.0` | `>=1.25.0-0` |
| `0.12.11` | `0.16.0` | `>=1.25.0-0` |
| `0.12.10` | `0.16.0` | `>=1.25.0-0` |
| `0.12.9` | `0.15.3` | `>=1.25.0-0` |
| `0.12.8` | `0.15.2` | `>=1.25.0-0` |
| `0.12.7` | `0.15.2` | `>=1.25.0-0` |
| `0.12.6` | `0.15.1` | `>=1.25.0-0` |
| `0.12.5` | `0.15.0` | `>=1.25.0-0` |
| `0.12.4` | `0.14.0` | `>=1.25.0-0` |
| `0.12.3` | `0.14.0` | `>=1.25.0-0` |
| `0.12.2` | `0.12.2` | `>=1.25.0-0` |
| `0.12.1` | `0.12.2` | `>=1.25.0-0` |
| `0.12.0` | `0.12.0` | `>=1.25.0-0` |
<!-- END generated: chart-release-history -->

Superseded (do not use): operator image `0.12.0`/`0.12.1`
(unsigned), and the `mcp-hangar` chart `0.12.0`/`0.13.0`/`0.13.1` (the `0.12.0`
chart pointed at a non-existent core image tag; `0.13.1` predates the install
fixes and still declares `appVersion 1.4.0`). The core image is versioned on its
own line, matching PyPI core release for release (see *Released artifacts*
above); its release workflow already cosign-signs and attaches build
provenance.

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
      (digests in *Released artifacts*). Both are long superseded — the current
      charts are in *Released artifacts*; `0.13.1` predates the install fixes.
- [x] The published charts install: the fixes found by live testing were verified
      present in `charts/mcp-hangar 0.13.4` and
      `charts/mcp-hangar-operator 0.12.3` by pulling and inspecting them while
      those were the published charts, and every chart released since builds on
      them.
- [x] **Chart releases are immutable** — the publish guard skips re-push of an
      already-published version (`mcp-hangar/helm-charts#36`, closed; fixed by the
      `crane manifest` probe in #37), so a released chart tag's digest is a stable
      pin.
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
