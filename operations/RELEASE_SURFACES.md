# Release surfaces

Every place a version number has to move when core ships, and the order to move
them in. This exists because they drift: after 2.5.0 the installation page still
narrated 2.4.0, and the released-artifacts matrix still showed 2.2.0.

There is no single source of truth spanning the repos, and building one would be
disproportionate — so this is the checklist instead.

## Order

Core first, satellites second. A satellite that advertises a version before the
artifact exists is worse than one that lags: `pip install mcp-hangar` will not
resolve it, and a chart pointing at an unpublished image fails its own smoke
test.

### 1 · Core — `mcp-hangar`

Release-please owns `.release-please-manifest.json` and `pyproject.toml`. Merging
its PR tags the release and the tag workflow publishes.

- **Promoting a candidate to stable needs a `Release-As:` footer.** After
  release-candidate commits, release-please proposes the *next patch candidate*
  (e.g. `2.5.1-rc.4`), not the stable promotion. Force it with an empty commit on
  `main` whose body is `Release-As: 2.5.0`, then let it re-run.
- Wait for the release workflow's **"Publish Docker Image"** job, not just
  "Publish to PyPI". Satellites reference the image.

### 2 · Satellites

| Surface | Where | Note |
| --- | --- | --- |
| Website advertised version | `mcp-hangar-website` → `packages/site/src/config.ts` → `VERSION` | Single constant; drives the hero badge, footer, quick-start and JSON-LD. **Stable releases only** — a candidate here sits beside an install command that will not produce it |
| Chart `appVersion` | `helm-charts` → `<chart>/Chart.yaml` | Bump `appVersion` **only**; release-please owns the chart's own `version` |
| Docs current version | this repo → `getting-started/installation.md`, `getting-started/releases.md` | Install command, `docker pull` tag, and the "stable core is X, released Y" line — the date moves too |
| Released-artifacts matrix | this repo → `operations/RELEASE_COMPATIBILITY.md` | Generated. Do not hand-edit; see below |

### 3 · The artifacts matrix lags on purpose

`sync-release-matrix` regenerates it from the registry, so it only tells the
truth once the artifacts are actually published — and GHCR's **tag listing is
eventually consistent**. A chart tag can be pullable minutes before `crane ls`
lists it. If a freshly published version is missing, re-run the workflow later
rather than editing the table.

## What does *not* need touching

Historical references. "On 2.4.0 and earlier", upgrade paths from 1.6.x, and
release-format examples in `development/CONTRIBUTING.md` are all correct as
written and should survive a version bump. A sweep that rewrites them is a
regression, not hygiene.
