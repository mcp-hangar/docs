# MCP Hangar Docs

Public documentation for MCP Hangar. Released by release-please as GitHub releases, and rendered on [mcp-hangar.io/docs](https://mcp-hangar.io/docs) by `mcp-hangar/mcp-hangar-website`, which installs `@mcp-hangar/docs` from this repository at a pinned commit SHA.

## Quick Reference

| Property | Value |
| --- | --- |
| Format | Markdown with frontmatter, lowercase kebab-case file names |
| Lint | `markdownlint-cli2` with `.markdownlint.jsonc` on every `*.md` outside `.github/` |
| Validators | seven scripts in `scripts/`, run by `validate-docs.yml` against checkouts of core and the operator |
| Release | release-please, `chore(release): release X.Y.Z`; `docs:` commits land under Changed |
| Owner | `@mapyr` reviews everything; `adr/`, `development/` and `operations/RELEASE_COMPATIBILITY.md` are CODEOWNERS-protected |

## Commands

Run from the repository root with a core checkout beside it (`--source`, or `MCP_HANGAR_SRC`) and an operator checkout for the manifest check. `promtool` must be on `PATH` for the PromQL check.

```bash
npx --yes markdownlint-cli2 "**/*.md" "!.github/**"
python scripts/check_links.py
python scripts/check_cli.py --docs . --source ../mcp-hangar
python scripts/check_manifests.py --docs . --operator ../operator
python scripts/check_promql.py --docs .
python scripts/check_freshness.py --selftest
python scripts/check_freshness.py --docs . --source ../mcp-hangar
python scripts/check_config.py --selftest
python scripts/check_config.py --docs . --source ../mcp-hangar
python scripts/validate_docs.py --docs . --source ../mcp-hangar
```

Baseline every check on a clean `origin/main` worktree before editing. Only a difference between the baseline run and your run is yours. `development/DOCS_VALIDATION.md` explains what each script covers and what still needs a human.

## Layout

```text
adr/              Architecture decision records and their index (human-authored)
architecture/     System design, policy model
cookbook/         Numbered recipes (PR scope: guides)
development/      Contributor governance: GIT_FLOW, BRANCH_PROTECTION, EPIC_PLAYBOOK, HOTFIX_RUNBOOK, DOCS_VALIDATION
getting-started/  Install and first run
guides/           Task-oriented how-tos
integrations/     Third-party adapters
observability/    Metrics, tracing, dashboards
operations/       Deployment, RELEASE_COMPATIBILITY.md (generated table)
reference/        CLI, config, API, tools
runbooks/         Operational procedures
security/         Threat model, controls, advisories
testing/          Test tiers and conformance
scripts/          The validators and the matrix generator
upgrade.md        Upgrade guide, one section per released core minor
changelog.md      Written by release-please
```

## Conventions

- Every page carries `title`, `description`, `sidebar_label` and `sidebar_order` in its frontmatter.
- Name only `hangar_*` tools, `mcp_hangar_*` metrics and `MCP_*`/`HANGAR_*` variables that exist in core. A deliberate exception (an old name in a migration table, a Proposed ADR's future tool) goes into `ALLOWLIST` in `scripts/validate_docs.py` with a justifying comment, in the same PR.
- A page that states a current version carries `<!-- verified-against: X.Y.Z -->`. The token says a human re-read the page; it is never bumped by a bot, and it fails the build once the released version is more than one minor ahead. Re-read the page against the tag, fix what changed, then move the token.
- `upgrade.md` must have a `## Upgrade to X.Y` section for every released minor. `sync-upgrade-guide.yml` brings over the section assembled from core's `upgrade.d/` notes; a release without steps still gets a one-line section.
- Verify behaviour against the released artifact (the wheel or image of the version the page names), not against a local core branch.
- Generated content is never hand-edited: the block between the `released-artifacts` markers in `operations/RELEASE_COMPATIBILITY.md` (`sync-release-matrix.yml`) and `changelog.md` (release-please).
- Tables use the compact pipe style (`| a | b |`, separator `| --- | --- |`); the linter enforces it. Blank lines around headings, lists, fences and tables; one trailing newline; no trailing punctuation in headings.
- No emoji. Public text says "a test Kubernetes cluster"; it never names a host or an IP.

## Pull requests

- Issue first; link it with `Closes #N`. Labels: one `type/*`, one `scope/*`, one `priority/*`.
- Branch `<type>/<slug>`. Title `<type>(<scope>): <lowercase subject>` with scope in `architecture`, `ci`, `deps`, `guides`, `infra`, `reference`, `release`, `repo`. There is no `cookbook` scope; recipes are `guides`.
- Body: `## Why` and `## How tested`, each with a prose sentence. A section that holds only a code block counts as empty.
- No changelog fragment here; the `pr-body` check is the gate. Squash-merge. Update a branch by merging `origin/main`, never by rebasing a pushed branch.
- An agent prepares the merge of a green PR, releases included, and the owner runs it; the classifier refuses `gh pr merge` from an agent. A PR refreshed by a bot force-push (release-please, the sync workflows) shows no checks until it is closed and reopened.
- After a core minor, merge the `chore/sync-upgrade-guide` PR first, with the re-read pages and their tokens on it; other open PRs then need `gh pr update-branch`.

## ADRs

`adr/ADR-NNN-<slug>.md` plus a row and summary in `adr/README.md` in the same PR. ADRs are human-authored: agents draft in issue comments and never open the PR unless the owner waives the rule for that ADR. Rules live in core's `docs/internal/ADR_AGENTS.md`. An Accepted ADR is immutable; amend by superseding. Title `docs(architecture): adr-NNN -- <decision>`.

## Workflows

| Workflow | Purpose |
| --- | --- |
| `lint.yml` | markdownlint-cli2 on every PR |
| `validate-docs.yml` | the seven validators, on PRs, pushes to `main` and weekly |
| `domain-lint.yml` | wording and domain checks |
| `branch-name.yml`, `pr-title.yml`, `pr-body.yml` | shared reusables from `mcp-hangar/.github` |
| `sync-upgrade-guide.yml` | daily and on dispatch: bring over a released upgrade section this repo is missing, open a PR on `chore/sync-upgrade-guide` |
| `sync-release-matrix.yml` | daily and on dispatch: regenerate the released-artifacts table from GHCR, open a PR |
| `release-please.yml` | release PR and GitHub release |
| `project-board.yml`, `stale.yml`, `dependabot-automerge.yml` | housekeeping |

## What NOT to Do

- Do not hand-edit `changelog.md` or the generated block of `operations/RELEASE_COMPATIBILITY.md`.
- Do not bump a `verified-against` token without re-reading the page against that version.
- Do not open an ADR PR as an agent without an explicit per-ADR waiver.
- Do not add a page without frontmatter or with a non-kebab-case name.
- Do not document a symbol core has not shipped without an `ALLOWLIST` entry.
- Do not rebase and force-push a pushed branch.
