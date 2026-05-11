# Contributing

Thanks for editing the MCP Hangar docs. This guide covers the basics —
authoring conventions, the PR flow, and where to discuss larger changes.

## Quick edits

For typos, broken links, clarifications, and missing examples:

1. Fork or branch.
2. Edit the relevant markdown file.
3. Open a PR with a Conventional Commit title (see below).
4. CI must pass — markdownlint and the link check.

No issue is required for small edits.

## Larger changes

Open an issue first for:

- Adding a new top-level section (a sibling to `guides/`, `reference/`, etc.).
- Renaming or moving a folder.
- Removing or merging content across multiple files.
- Changes that affect cross-links from `mcp-hangar.io` (route shape changes).

This avoids invalidating bookmarks and gives time to coordinate with the
website team if the structural change requires a corresponding update in
[mcp-hangar-website](https://github.com/mcp-hangar/mcp-hangar-website).

## PR title — Conventional Commits

PR titles are enforced by the `pr-title` workflow. Format:

```
<type>(<scope>): <subject>
```

**Types:** `feat`, `fix`, `docs`, `chore`, `ci`, `refactor`, `revert`.

**Scopes** (optional but encouraged) — match the section being edited:
`architecture`, `getting-started`, `guides`, `operations`, `observability`,
`security`, `runbooks`, `development`, `reference`, `cookbook`, `adr`,
`integrations`, `testing`, `blog`, `repo`, `ci`, `deps`, `release`.

**Subject:** start with a lowercase letter. Imperative mood ("fix" not "fixes").

Examples:

```
docs(guides): clarify webhook signing key rotation
fix(reference): correct env var name in CLI table
chore(repo): bump markdownlint-cli2 to v0.13
```

## Markdown conventions

- ATX headings (`#`, `##`, …), no setext.
- Fenced code blocks with language hint (`` ```python ``, `` ```bash ``).
- Relative links between docs in this repo (`[X](../guides/X.md)`).
- Absolute URLs for links to other repos
  (`https://github.com/mcp-hangar/mcp-hangar/blob/main/AGENTS.md`).
- One sentence per line is fine but not required; markdownlint allows long
  lines (MD013 disabled).
- HTML is permitted only for: `<br>`, `<details>`, `<summary>`, `<kbd>`,
  `<sub>`, `<sup>`.

## Frontmatter

Conventions are still being finalized as content is migrated. The current
expected fields are:

```yaml
---
title: Page title (string, required)
description: One-sentence summary for search snippets (string, recommended)
sidebar_order: 10           # ordering within the section (int, optional)
---
```

Frontmatter schemas are codified in `mcp-hangar-website` when the Astro
content loader lands — see
[mcp-hangar/mcp-hangar-website#43](https://github.com/mcp-hangar/mcp-hangar-website/issues/43).

## Local preview

Markdown renders well in any editor with a preview pane (VS Code, JetBrains
IDEs). Full website rendering happens in `mcp-hangar-website` against a
locally-linked copy of this repo via `pnpm link` (see the website README).

## Release flow

This repo cuts independent releases. After your PR merges to `main`:

1. A maintainer pushes a tag matching `v*.*.*`.
2. The publish workflow ships `@mcp-hangar/docs@<tag>` to npm with sigstore
   provenance.
3. `mcp-hangar-website` bumps its dependency in a follow-up PR; the change
   goes live on `mcp-hangar.io` after that PR merges.

There is no obligation to cut a release immediately after every PR — releases
are batched at the maintainer's discretion.

## Code of Conduct

We follow the [Contributor Covenant](https://www.contributor-covenant.org/).
Be kind. Disagreements happen; keep them in the issue or PR thread.

## Security

If you find a security issue in MCP Hangar itself (the runtime, agent,
operator, or terraform provider), do not open a public issue. See the
security policy in [mcp-hangar/mcp-hangar](https://github.com/mcp-hangar/mcp-hangar/security)
for the disclosure procedure.

Documentation bugs (incorrect security recommendations, misleading examples
that could lead to insecure deployments) are public-issue-friendly — open one
here.
