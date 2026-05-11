# MCP Hangar Documentation

Canonical source of truth for public-facing MCP Hangar documentation. Content
authored here is published as the `@mcp-hangar/docs` npm package on every
tagged release and consumed by [mcp-hangar.io](https://mcp-hangar.io/docs).

## What lives here

Public, user-facing documentation only:

| Section | Audience |
|---|---|
| `architecture/` | Engineers reading the system's design |
| `getting-started/` | New users installing MCP Hangar for the first time |
| `guides/` | Task-oriented how-tos |
| `operations/` | Operators running Hangar in production |
| `observability/` | Metrics, tracing, audit, compliance export |
| `security/` | Hardening, supply chain, vulnerability disclosure |
| `runbooks/` | On-call response procedures |
| `development/` | Contributor workflow, git flow, branch protection |
| `reference/` | API, CLI, configuration, tools |
| `cookbook/` | End-to-end worked examples |
| `adr/` | Architecture Decision Records |
| `integrations/` | Third-party integrations (Langfuse, Tetragon, …) |
| `testing/` | Test strategy, fixtures, harnesses |

Internal contributor notes (architecture deep dives, agent instructions,
Copilot guidance) live in the [`mcp-hangar`](https://github.com/mcp-hangar/mcp-hangar)
repo under `docs/internal/` and never ship in the npm package.

## How content flows

```
                                   ┌──────────────────────────┐
                                   │  mcp-hangar/docs (here)  │
                                   │                          │
                                   │   Markdown + frontmatter │
                                   └────────────┬─────────────┘
                                                │ tag v*.*.*
                                                ▼
                          ┌────────────────────────────────────────────┐
                          │  CI: npm publish --provenance              │
                          │  → @mcp-hangar/docs@<tag> on registry      │
                          └─────────────────────┬──────────────────────┘
                                                │ pnpm add
                                                ▼
                                ┌───────────────────────────────┐
                                │   mcp-hangar-website          │
                                │   Astro content loader        │
                                │   → renders on mcp-hangar.io  │
                                └───────────────────────────────┘
```

## Versioning

This repo follows semantic versioning **independently** of `mcp-hangar` core
releases. Typo fixes ship as patch bumps without requiring a Hangar version
bump. The website pins to a specific `@mcp-hangar/docs` version, so docs
changes only land on `mcp-hangar.io` when the site dependency is bumped.

Releases are cut by pushing a tag matching `v*.*.*`. The publish workflow
produces an npm package with [sigstore](https://www.sigstore.dev/) provenance
attestation.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full guide. Quick start:

1. Open a PR with your edits.
2. PR title follows Conventional Commits (e.g. `docs(guides): fix typo in
   webhook example`).
3. CI runs markdownlint + a link check; both must pass.
4. Reviewer merges; the next release tag publishes a new package version.

Large structural changes (adding a new top-level section, renaming a folder,
moving content between sections) should be discussed in an issue first.

## Related repos

| Repo | Role |
|---|---|
| [mcp-hangar/mcp-hangar](https://github.com/mcp-hangar/mcp-hangar) | Python core — the runtime |
| [mcp-hangar/mcp-hangar-website](https://github.com/mcp-hangar/mcp-hangar-website) | Astro site at `mcp-hangar.io` — consumer of this package |
| [mcp-hangar/mcp-hangar-agent](https://github.com/mcp-hangar/mcp-hangar-agent) | Go data-plane sidecar |
| [mcp-hangar/mcp-hangar-operator](https://github.com/mcp-hangar/mcp-hangar-operator) | Kubernetes operator |
| [mcp-hangar/helm-charts](https://github.com/mcp-hangar/helm-charts) | Helm charts |
| [mcp-hangar/terraform-provider](https://github.com/mcp-hangar/terraform-provider) | Terraform provider |
| [mcp-hangar/benchmarks](https://github.com/mcp-hangar/benchmarks) | Performance benchmarks |

## License

MIT. See [`LICENSE`](./LICENSE).
