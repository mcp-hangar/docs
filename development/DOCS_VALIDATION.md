# Documentation Validation

These docs are published independently of the [`mcp-hangar`][src] product, so
they can drift: a symbol gets renamed or removed in the code, but the docs keep
referencing the old name. This page describes the control that catches that
drift and the review steps that automation cannot cover.

[src]: https://github.com/mcp-hangar/mcp-hangar

## Automated check

`scripts/validate_docs.py` extracts high-signal identifiers from every Markdown
file and verifies each one still exists in the product source tree. It runs in
CI (`.github/workflows/validate-docs.yml`) on every pull request, on push to
`main`, and weekly, and fails the build on any "phantom" reference.

It checks three identifier classes, chosen because they grep cleanly with a low
false-positive rate:

| Class | Pattern | Notes |
| --- | --- | --- |
| MCP tools | `hangar_*` | Must appear as a registered tool name in source. |
| Prometheus metrics | `mcp_hangar_*` | The Counter `_total`/`_seconds`/etc. suffix is appended at exposition, so the base name is matched. |
| Environment variables | `MCP_*`, `HANGAR_*` | `${VAR}` config-interpolation placeholders are ignored (those are user-chosen, not Hangar's own vars). |

The `changelog.md` is excluded (it is an immutable historical record that names
removed symbols on purpose). Deliberate exceptions -- old tool names in
migration tables, example-only env vars -- live in the `ALLOWLIST` near the top
of the script, each with a justifying comment.

### Running it locally

```bash
# Default source path is ../mcp-hangar
python scripts/validate_docs.py

# Or point at an explicit checkout
python scripts/validate_docs.py --source /path/to/mcp-hangar
# or: MCP_HANGAR_SRC=/path/to/mcp-hangar python scripts/validate_docs.py
```

Exit `0` = clean, `1` = phantom reference(s) found. When a finding is a genuine
rename, fix the doc; when it is an intentional historical/example reference, add
it to `ALLOWLIST`.

## What automation does NOT cover

The validator catches renamed/removed *symbols*. It cannot judge structure or
prose. Review these by hand when the product changes, or when touching the
relevant docs:

- **REST / WebSocket routes** -- path + method + `/api` prefix. Verify against
  `src/mcp_hangar/server/api/` route definitions and the `/api` mount in
  `server/lifecycle.py`.
- **Nested config keys** -- YAML structure under `mcp_servers`, `auth`,
  `discovery`, etc. Verify against the config parsers in
  `src/mcp_hangar/server/config.py` and the relevant value objects.
- **Class / event / enum names** in architecture docs and ADRs.
- **Version and changelog accuracy** -- the `changelog.md` should mirror the
  authoritative release-please `CHANGELOG.md` in the product repo; cookbook /
  guide version claims should match the release a feature actually shipped in.

## When the product changes

1. Run the validator locally against your `mcp-hangar` checkout.
2. Fix any phantom symbol references it reports.
3. Manually review the structural items above for the area you changed.
4. If a feature shipped in a new release, update `changelog.md` to mirror the
   product `CHANGELOG.md`, and check that any cookbook/guide that references a
   version names the release the feature actually shipped in.
