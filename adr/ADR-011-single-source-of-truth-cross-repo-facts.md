# ADR-011: Single Source of Truth for Cross-Repo Facts

**Status:** Accepted
**Date:** 2026-07-18
**Authors:** MCP Hangar Team

## Context

MCP Hangar spans several repositories -- core (`mcp-hangar`), the operator, `helm-charts`, `docs`, and the website. A number of facts appear in more than one of them: the canonical domain, released versions and their digests, install commands, server security behavior, and version/appVersion compatibility.

Today each of those facts is **hand-copied** into every place it appears, and each copy drifts independently:

- **Domain** -- prose said `mcp-hangar.io`, a release template said `mcp-hangar.github.io`, and the website repo's `homepage` was `mcp-hangar-website.vercel.app`: three domains, none designated canonical (mcp-hangar#486).
- **Chart versions** -- the `helm-charts` README hardcodes `--version` numbers that diverge from the release tags in the same repo; the operator's compatibility row was stale one day after the release cut (helm-charts#44).
- **Install commands** -- pinned (`--version X`) in the `helm-charts` README, unpinned in the operator README: two hand-written variants of the same command (mcp-hangar-operator#36).
- **`--http` auth requirement** -- the fail-closed behavior is documented in `helm-charts` (README + `NOTES.txt`) but silent in the core README (mcp-hangar#485).

There is also a reachability gap: `docs/operations/RELEASE_COMPATIBILITY.md` reconciles the repos' versions and is generated in CI (docs#56), but core links to `docs` for GIT_FLOW, ADRs, and CONTRIBUTING and **never** for the matrix -- the flagship repo has no path to the one artifact that reconciles versions.

These are four symptoms of one defect: **there is no designated owner for any cross-repo fact, so every fact is copied and drifts.** Fixing the four values by hand just resets the clock until the next release.

## Decision

**Every cross-repo fact has exactly one owner. Everything else generates-from or links-to that owner and never duplicates the value. Where a value cannot be a link (it must appear literally, e.g. a domain in a template), a CI lint prevents regression.**

Preference order for consuming a fact: **link > generate > hand-copy.** A hand-copied cross-repo value is treated as a defect.

| Fact | Owner (SSOT) | How every other repo consumes it |
|------|--------------|----------------------------------|
| **Domain** | the constant `mcp-hangar.io` | Published docs and templates use it verbatim. A reusable CI lint rejects `*.github.io`, `*.vercel.app`, and `mcp-hangar.github.io` in tracked docs, so no other domain can regress in. |
| **Released versions & digests** | the release-please manifests + GHCR, materialized into `docs/operations/RELEASE_COMPATIBILITY.md` (generated in CI, docs#56) | READMEs carry **no** hardcoded version numbers; they link to the releases page / the matrix. |
| **Install commands** | one canonical **unpinned** snippet per artifact | The `helm-charts` and operator READMEs use the same snippet plus a note to pin a version from the compatibility matrix -- not two hand-written variants. |
| **Server security behavior** (fail-closed `--http` auth, etc.) | the **core** README | Charts (README + `NOTES.txt`) **link** to the core README instead of re-documenting the behavior. |
| **Version / appVersion compatibility** | `RELEASE_COMPATIBILITY.md` | Reachable **from the core README** -- the flagship's entry point into the matrix. |

## Consequences

### Resolved as implementations of this ADR (not one-off edits)

- **mcp-hangar#486** (domain) -- reusable domain lint + one caller per repo.
- **helm-charts#44** (chart versions) -- drop the numbers from the README; link to the releases page / matrix.
- **mcp-hangar-operator#36** (install command) -- a single unpinned snippet plus the pin-from-matrix note, shared by both READMEs.
- **mcp-hangar#485** (`--http` auth) -- documented in the core README (the SSOT); charts link to it.
- The compatibility matrix is linked from the core README.

Each symptom issue is closed by *generate-from / link-to the owner*, never by re-copying the value.

### Costs and trade-offs (accepted)

- **Drop-and-link** means a reader clicks through to find the current version rather than reading it inline. Zero drift is worth one click.
- **Unpinned** install snippets install the latest chart; a reproducible deploy requires pinning a version from the matrix -- the snippet's note says so, rather than baking in a number that goes stale.
- A new reusable CI lint to maintain in `.github`, plus one thin caller per repo.

### Explicitly unaffected

- The generated-matrix mechanism (docs#56) and release-please as the versioning SSOT are unchanged; this ADR only *designates* the matrix the versions/compat owner and makes it reachable from core.
- Per-repo content that is genuinely local (not a shared fact) is out of scope.

## References

- Governing epic: [mcp-hangar#501](https://github.com/mcp-hangar/mcp-hangar/issues/501) -- this ADR is its "governing decision".
- Symptom issues: mcp-hangar#485, mcp-hangar#486, helm-charts#44, mcp-hangar-operator#36.
- Matrix generator: docs#56. Related: [ADR-009](ADR-009-independent-release-topology.md) (independent release topology).
