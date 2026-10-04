# Release Operations Runbook

This runbook covers operational procedures for releasing MCP Hangar.

## Table of Contents

- [Standard Release](#standard-release)
- [Emergency Hotfix](#emergency-hotfix)
- [Release Rollback](#release-rollback)
- [Troubleshooting](#troubleshooting)

---

## Standard Release

### Prerequisites

- [ ] All CI checks passing on `main` branch
- [ ] Every non-trivial PR merged since the last release added its fragment in `changelog.d/` (`CHANGELOG.md` is never edited by hand)
- [ ] No blocking issues in milestone

### Procedure

#### Step 1: Verify Main Branch State

```bash
git checkout main
git pull origin main
git status  # Should be clean

# Run full test suite
uv run pytest tests/ -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

#### Step 2: Initiate Release (Automated via release-please)

Releases are driven by [release-please](https://github.com/googleapis/release-please) (`.github/workflows/release-please.yml`). When Conventional Commit PRs merge to `main`, release-please opens a release PR, `chore(release): release X.Y.Z`, that bumps `pyproject.toml`, `server.json` and `uv.lock`. The same workflow folds the `changelog.d/` fragments into a `CHANGELOG.md` section on that PR. Merging it makes release-please push the `vX.Y.Z` tag and create the GitHub Release, and the tag triggers the release pipeline.

#### Step 3: Monitor Release Pipeline

After version tag is pushed, the Release workflow triggers automatically:

1. **Validate** — Checks tag matches pyproject.toml
2. **Test** — Runs full test matrix (Python 3.11-3.14)
3. **Smoke the wheel** — Builds the wheel, installs it in a clean venv and drives a real tool call, before anything is published
4. **Publish PyPI** — Builds, attests and uploads to PyPI
5. **Publish to MCP Registry** — Stable releases only; checks that `server.json` matches the tag
6. **Publish Docker** — Builds multi-arch images (amd64, arm64), pushes to GHCR, signs them with cosign
7. **Create Release** — Updates the GitHub Release with the changelog section, the wheel, the sdist and the provenance bundle
8. **Smoke published** — Installs what PyPI serves and drives a tool call again

Monitor at: `https://github.com/mcp-hangar/mcp-hangar/actions`

#### Step 4: Verify Artifacts

```bash
# Verify PyPI package
pip install mcp-hangar==<VERSION> --dry-run

# Verify Docker image
docker pull ghcr.io/mcp-hangar/mcp-hangar:<VERSION>
docker run --rm ghcr.io/mcp-hangar/mcp-hangar:<VERSION> --version
```

#### Step 5: Post-Release

- [ ] Verify GitHub Release page has correct changelog
- [ ] Update documentation site if needed
- [ ] Announce in relevant channels (Discord, Slack, etc.)
- [ ] Close milestone in GitHub

---

## Emergency Hotfix

Use this procedure for critical bugs in production releases.

### Severity Assessment

| Severity | Description | Response Time |
| ---------- | ------------- | --------------- |
| P0 | Security vulnerability, data loss | Immediate |
| P1 | Major functionality broken | < 4 hours |
| P2 | Significant bug, workaround exists | < 24 hours |

### Procedure

#### Step 1: Create Hotfix Branch

```bash
# From the affected version tag
git fetch --tags
git checkout -b hotfix/X.Y.Z vX.Y.Z-1  # e.g., hotfix/1.0.1 from v1.0.0
```

#### Step 2: Apply Fix

```bash
# Make minimal fix, add regression test
# ...

# Run tests
uv run pytest tests/ -v

git add -A
git commit -m "fix(<scope>): description of fix"
```

#### Step 3: Update Version and Changelog

```bash
# Update the version everywhere the pipeline checks it. Anchored: an
# unanchored pattern also rewrites ruff's target-version and mypy's python_version.
perl -pi -e 's/^version = ".*"/version = "X.Y.Z"/' pyproject.toml
perl -pi -e 's/"version": "[^"]*"/"version": "X.Y.Z"/' server.json   # both fields
uv lock                                                                # mcp-hangar's own entry

# Add a `## [X.Y.Z] - YYYY-MM-DD` section, with a `### Fixed` entry, at the top
# of the version sections in CHANGELOG.md: the release job copies that section
# into the GitHub Release.
```

#### Step 4: Tag and Push

```bash
git add pyproject.toml server.json uv.lock CHANGELOG.md
git commit -m "chore(release): release X.Y.Z"
git tag -a vX.Y.Z -m "Hotfix: description"
git push origin hotfix/X.Y.Z
git push origin vX.Y.Z
```

#### Step 5: Bring the Fix to Main

Open a PR to `main` with the fix commit only, so commit the fix and the version
bump separately on the hotfix branch. The version files on `main` belong
to release-please, so do not carry the bump over, and do not push to `main`
directly: the PR runs the required checks.

```bash
git checkout -b fix/<scope>-<slug> origin/main
git cherry-pick <fix-commit-hash>
git push origin fix/<scope>-<slug>
```

---

## Release Rollback

If a release introduces critical issues that can't be hotfixed quickly.

### PyPI Rollback

PyPI doesn't allow re-uploading deleted versions. Instead:

1. **Yank the version** (marks as not recommended):

   Use the PyPI web interface: navigate to `https://pypi.org/manage/project/mcp-hangar/release/X.Y.Z/`, then click "Yank". There is no CLI command for yanking.

2. **Release a new patch version** with the fix or revert.

### Docker Rollback

1. **Update `latest` tag** to previous stable version. Retag the multi-arch
   manifest in the registry; `docker pull`, `tag` and `push` would republish
   `latest` for one architecture only:

   ```bash
   docker buildx imagetools create -t ghcr.io/mcp-hangar/mcp-hangar:latest \
     ghcr.io/mcp-hangar/mcp-hangar:X.Y.Z-1
   ```

2. **Document the issue** in GitHub Release notes.

### Communication

- Update GitHub Release to mark as "Known Issues"
- Post in announcement channels with:
  - Affected versions
  - Impact description
  - Recommended action (upgrade to X.Y.Z+1 or pin to X.Y.Z-1)

---

## Troubleshooting

### Release Workflow Failures

#### Test Failures

```
Error: Tests failed on Python 3.X
```

**Resolution:**

1. Check test logs in Actions
2. Reproduce locally: `uv run pytest tests/ -v --tb=long`
3. A flaky failure: re-run the failed jobs of the Release run. PyPI publishing
   uses `skip-existing`, so a re-run never fails on an upload that already happened.
4. A real defect: fix it on `main` and release the next patch. Do not move the
   tag: release-please has already created the GitHub Release for it.

#### PyPI Publish Failure

```
Error: 403 Forbidden - trusted publishing not configured
```

**Resolution:**

1. Verify PyPI Trusted Publisher is configured:
   - Go to PyPI → Project → Publishing
   - Add GitHub publisher: `mcp-hangar/mcp-hangar`, workflow `release.yml`
2. Ensure `environment: pypi` is set in workflow

#### Docker Build Failure

```
Error: buildx failed for linux/arm64
```

**Resolution:**

1. Check if Dockerfile has architecture-specific dependencies
2. May need to add platform-specific build stages
3. Consider removing arm64 from platforms temporarily

### Version Mismatch

```text
Version mismatch!
   pyproject.toml: X.Y.Z
   Git tag: X.Y.W
```

**Resolution:**

1. Either update `pyproject.toml` to match tag
2. Or delete tag and re-create with correct version:

   ```bash
   git push origin :refs/tags/vX.Y.W
   git tag -d vX.Y.W
   ```

### Manual Intervention Required

If automated workflows fail and manual release is needed:

```bash
# Build package
python -m build

# Upload to PyPI (requires API token)
twine upload dist/*

# Build and push Docker
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/mcp-hangar/mcp-hangar:X.Y.Z \
  -t ghcr.io/mcp-hangar/mcp-hangar:latest \
  --push .
```

---

## Contacts

| Role | Contact |
| ------ | --------- |
| Release Manager | @maintainer |
| Security Issues | [GitHub Security](https://github.com/mcp-hangar/mcp-hangar/security) |
| Infrastructure | @infra-team |

---

## Changelog

| Date | Change | Author |
| ------ | -------- | -------- |
| 2026-01-12 | Initial runbook creation | CI/CD Setup |
