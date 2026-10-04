# Branch Protection

## Purpose

Branch protection on `main` in `mcp-hangar/mcp-hangar` ensures that every commit landing in the default branch has passed the full CI validation suite. It prevents direct pushes, enforces linear history (squash-merge; rebase-merge is disabled), and requires conversation resolution before merge.

## Current configuration

Two layers apply to `main`, and both must pass.

Classic branch protection:

- Required status checks (strict — branch must be up to date): the 14 listed below
- Required approving reviewers: 0
- Require code owner reviews: false
- Enforce admins: **true**
- Required linear history: true
- Allow force pushes: false
- Allow deletions: false
- Block creations: false
- Required conversation resolution: true

Repository rulesets, both with an always-bypass for the admin role:

- `main` (default branch): no deletion, no force push.
- `main-integrity` (`refs/heads/main`): no deletion, no force push, linear
  history, the same 14 status checks (strict), and a pull request with 0
  approvals and every review thread resolved.

Read the live state with `gh api repos/mcp-hangar/mcp-hangar/branches/main/protection`
and `gh api repos/mcp-hangar/mcp-hangar/rules/branches/main`.

## Required status checks

The context is the job name; a check from a reusable workflow is
`<calling job> / <reusable job>`.

| Check name | Workflow file | What it enforces |
| --- | --- | --- |
| `required-check` | `pr-validation.yml` | Paths-filter summary gate |
| `check` | `changelog-check.yml` | Changelog fragment present in `changelog.d/` |
| `pr-title / validate` | `pr-title.yml` | Conventional Commits title |
| `branch-name / validate` | `branch-name.yml` | Branch naming convention |
| `pr-body / validate` | `pr-body.yml` | PR body section structure |
| `lint` | `ci-core.yml` | ruff check and format, mypy, import contracts |
| `test (3.11)`, `test (3.12)`, `test (3.13)`, `test (3.14)` | `ci-core.yml` | Tests per Python version; on a pull request 3.12 and 3.13 report a skip and run on `main` only |
| `decision-coverage` | `ci-core.yml` | Branch-coverage floors on decision paths |
| `integration`, `integration-newest` | `ci-core.yml` | Integration tests |
| `build` | `ci-core.yml` | Package build |

## Solo vs community mode

| Setting | Solo | Community |
| --- | --- | --- |
| Required approving reviewers | 0 | 1 |
| Require code owner reviews | false | true |
| Enforce admins | false | true |

These are the script's two modes. The live setting matches neither: 0
reviewers and no code owner reviews, as in solo, but `enforce_admins: true`, as
in community.

Flip to community mode when there is at least one second maintainer. Until then `require_code_owner_reviews: true` would block all merges to CODEOWNERS-protected paths since GitHub does not allow self-approval.

## Applying the protection

`scripts/setup-branch-protection.sh` has not kept up: it still writes the six
checks of an older layout, two of which (`pr-validation / required-check` and
`enterprise-boundary`) no job reports, and its solo mode sets
`enforce_admins: false`. Running it replaces the live list above. Update its
`contexts` array before running it; the rulesets are not managed by the script.

```bash
bash scripts/setup-branch-protection.sh
bash scripts/setup-branch-protection.sh --mode community
bash scripts/setup-branch-protection.sh --dry-run
```

## Adding a new required check

1. Merge the workflow producing the check.
2. Wait for at least one PR to run it green.
3. Add the check name to the `contexts` array in `scripts/setup-branch-protection.sh`.
4. Re-run the script.
5. Add it to the `main-integrity` ruleset too. The ruleset carries its own copy
   of the required checks, which the script never touches.

## Removing a required check

1. Comment out (do not delete) the check name in the script.
2. Re-run the script to apply the reduced list.
3. Remove it from the `main-integrity` ruleset, which the script does not
   change; a check still listed there stays required.
4. Delete or disable the workflow file in a separate PR.

## Emergency bypass

The live setting is `enforce_admins: true`, so the classic protection applies to admins as well, and a direct `git push origin main` is not an option while it is set; the rulesets' admin bypass does not lift the classic protection. Use only when CI itself is broken or a critical hotfix cannot wait. Bypass requires:

1. Temporarily set `enforce_admins: false` via GitHub UI.
2. Perform the emergency action.
3. Set `enforce_admins` back to `true` in the GitHub UI, or with
   `gh api -X POST repos/mcp-hangar/mcp-hangar/branches/main/protection/enforce_admins`.
   Do not restore it by re-running the script, which also rewrites the
   required checks and the review settings.
