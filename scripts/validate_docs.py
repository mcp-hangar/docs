#!/usr/bin/env python3
"""Validate MCP Hangar docs against the product source tree.

This is a *drift detector*. It extracts high-signal identifiers from the
Markdown docs and checks that each one still exists in the `mcp-hangar`
source repository. It catches the most common class of documentation rot:
a symbol gets renamed or removed in the product, but the docs keep
referencing the old name (a "phantom" reference).

What it checks (low false-positive rate by design):
  * MCP tool names         -- `hangar_*`
  * Prometheus metrics     -- `mcp_hangar_*` (handles the Counter `_total` suffix)
  * Environment variables  -- `MCP_*` / `HANGAR_*`

What it deliberately does NOT check (needs human review -- see
development/DOCS_VALIDATION.md): REST/WS route paths, nested YAML config
keys, prose accuracy, and version/changelog correctness. Those are too
structural to grep without noise.

Usage:
    python scripts/validate_docs.py [--source PATH] [--docs PATH] [--quiet]

Source path resolution order: --source, $MCP_HANGAR_SRC, ../mcp-hangar.
Exit code 0 = clean, 1 = phantom reference(s) found, 2 = bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Identifiers that legitimately appear in docs but are NOT live source symbols
# (historical migration tables, example-only env vars, etc.). Keep this list
# short and justified -- every entry is a check we are consciously skipping.
ALLOWLIST: set[str] = {
    # Old tool names kept in migration / "before -> after" tables.
    "hangar_invoke",
    "hangar_batch",
    # Example container env var in cookbook/04 (belongs to the demo image,
    # not to Hangar itself).
    "MCP_PORT",
    # This validator's own source-path override, documented in
    # development/DOCS_VALIDATION.md -- a docs-tooling var, not a product var.
    "MCP_HANGAR_SRC",
}

# Docs files excluded from symbol validation. The changelog is an immutable
# historical record and intentionally names removed/renamed symbols.
EXCLUDED_DOCS = {"changelog.md"}

TOOL_RE = re.compile(r"\bhangar_[a-z][a-z0-9_]*")
METRIC_RE = re.compile(r"\bmcp_hangar_[a-z][a-z0-9_]*")
ENV_RE = re.compile(r"\b(?:MCP|HANGAR)_[A-Z][A-Z0-9_]+")
# `${VAR}` in a config example is a user-chosen interpolation placeholder, not
# one of Hangar's own env vars -- strip those spans before extracting env vars.
INTERP_RE = re.compile(r"\$\{[^}]*\}")

# Metric suffixes that Prometheus client libs append at exposition time, so the
# base name (without the suffix) is what appears in the source definition.
METRIC_SUFFIXES = ("_total", "_seconds", "_bucket", "_count", "_sum", "_info")

SOURCE_GLOBS = ("*.py", "*.yaml", "*.yml", "*.toml")


def resolve_source(arg: str | None) -> Path:
    candidate = arg or os.environ.get("MCP_HANGAR_SRC") or "../mcp-hangar"
    path = Path(candidate).expanduser().resolve()
    if not (path / "src" / "mcp_hangar").is_dir():
        sys.exit(
            f"error: '{path}' does not look like the mcp-hangar source repo "
            f"(missing src/mcp_hangar/). Pass --source or set MCP_HANGAR_SRC."
        )
    return path


def load_source_blob(source: Path) -> str:
    parts: list[str] = []
    for pattern in SOURCE_GLOBS:
        for f in source.rglob(pattern):
            if any(seg in {".git", "__pycache__", "node_modules"} for seg in f.parts):
                continue
            try:
                parts.append(f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(parts)


def iter_doc_files(docs: Path):
    for f in sorted(docs.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def metric_present(name: str, blob: str) -> bool:
    if name in blob:
        return True
    for suffix in METRIC_SUFFIXES:
        if name.endswith(suffix) and name[: -len(suffix)] in blob:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Path to the mcp-hangar source repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    source = resolve_source(args.source)
    docs = Path(args.docs).expanduser().resolve()
    blob = load_source_blob(source)

    # category -> identifier -> sorted list of "file:line" doc locations
    findings: dict[str, dict[str, list[str]]] = {"tool": {}, "metric": {}, "env": {}}

    checks = (
        ("tool", TOOL_RE, lambda n: n in blob),
        ("metric", METRIC_RE, lambda n: metric_present(n, blob)),
        ("env", ENV_RE, lambda n: n in blob),
    )

    scanned = 0
    for doc in iter_doc_files(docs):
        scanned += 1
        rel = doc.relative_to(docs)
        for lineno, line in enumerate(doc.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            env_line = INTERP_RE.sub("", line)
            for category, regex, exists in checks:
                target = env_line if category == "env" else line
                for match in regex.findall(target):
                    if match in ALLOWLIST or exists(match):
                        continue
                    findings[category].setdefault(match, []).append(f"{rel}:{lineno}")

    total = sum(len(v) for v in findings.values())
    labels = {"tool": "MCP tools", "metric": "Prometheus metrics", "env": "env vars"}

    if not args.quiet:
        print(f"docs:   {docs}")
        print(f"source: {source}")
        print(f"scanned {scanned} markdown files\n")

    if total == 0:
        print("OK: no phantom references found.")
        return 0

    print(f"FAIL: {total} phantom reference(s) not found in source:\n")
    for category in ("tool", "metric", "env"):
        items = findings[category]
        if not items:
            continue
        print(f"  {labels[category]}:")
        for name in sorted(items):
            locs = ", ".join(items[name][:5])
            extra = "" if len(items[name]) <= 5 else f" (+{len(items[name]) - 5} more)"
            print(f"    - {name}  ->  {locs}{extra}")
        print()
    print("If a finding is a deliberate historical/example reference, add it to")
    print("ALLOWLIST in scripts/validate_docs.py with a justifying comment.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
