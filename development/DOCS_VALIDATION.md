# Documentation Validation

These docs are published independently of the [`mcp-hangar`][src] product, so
they can drift: a symbol gets renamed or removed in the code, but the docs keep
referencing the old name. This page describes the control that catches that
drift and the review steps that automation cannot cover.

[src]: https://github.com/mcp-hangar/mcp-hangar

## Automated checks

Two scripts run in CI (`.github/workflows/validate-docs.yml`) on every pull
request, on push to `main`, and weekly. They are separate because they need
different things: the link checker needs only this repository, the drift
detector needs the product source tree checked out beside it.

### Links and anchors

`scripts/check_links.py` resolves every relative link, and for a Markdown target
also the `#anchor`, against the headings that file actually produces. Run it
locally with no arguments and no product checkout:

```bash
python scripts/check_links.py
```

Two things it does that are easy to get wrong, both found by running it against
this repository rather than by reasoning:

- an underscore survives slugging, so a heading written as `startup_checks` in
  backticks becomes `#startup_checks`. Stripping the underscore as emphasis
  markup reported eight live anchors as broken.
- an explicit `{#custom-id}` on a heading wins over the slug. `reference/tools.md`
  uses 22 of them; without honouring those, every link into that page failed.

External URLs are not checked -- liveness is flaky, rate-limited and needs the
network. Bare `#fragment` self-links are not checked either: the renderer emits
ids for things that are not headings, so the heading set is not the full anchor
set for a link into the same page.

If the extraction ever matches nothing, the script **fails** rather than
reporting success over an empty set. A gate that cannot fail is not a gate.

### CLI commands

`scripts/check_cli.py` checks that every `mcp-hangar <command>` a bash block
tells the reader to run is a command the CLI actually registers, including the
second level for groups (`auth`, `completion`).

```bash
python scripts/check_cli.py --source /path/to/mcp-hangar
```

**Extraction is from ```bash fences only, and that is the whole difficulty.** A
naive `mcp-hangar\s+(\w+)` over the full text reports sixteen phantom
subcommands -- `mcp-hangar resource`, `mcp-hangar spec`, `mcp-hangar kubectl` --
every one of them prose or a YAML fragment that happens to follow the product
name. A gate that noisy gets switched off, so the match must sit where a command
sits: at the start of a line, or after a pipe, `&&`, `;`, `sudo`, or a prompt.

The command set is parsed out of the CLI source rather than imported, because
this job checks the product out but does not install it. That tradeoff has one
failure mode -- a change in how commands are registered would stop finding them
-- so the script **fails when it finds implausibly few** rather than approving
everything by default.

### Kubernetes manifests

`scripts/check_manifests.py` validates every `mcp-hangar.io` manifest in a
```yaml fence against the operator's CRDs -- the kind, the `apiVersion`, every
`spec` key, and every key one level into `spec.capabilities`.

```bash
python scripts/check_manifests.py --operator /path/to/mcp-hangar-operator
```

The schema is read from the operator repository's `config/crd/bases`, never
from a copy kept here. A copied schema drifts, and a drifted schema is a gate
that approves the wrong thing.

**Served is not the same as current.** `v1alpha1` is still served for
conversion, so a manifest using it is valid to the API server and is still the
wrong thing to teach -- that is the defect the product's own
`examples/kubernetes/` carried until mcp-hangar/mcp-hangar#928. The gate
therefore requires the *storage* version, not merely a served one.

Kubernetes' own kinds sharing a fence -- `Secret`, `ConfigMap`, `Deployment` --
are not checked. Those are the API server's schema, and `kubeconform` is the
tool for that if it is ever wanted.

### Symbol drift

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
