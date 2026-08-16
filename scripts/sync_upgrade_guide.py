#!/usr/bin/env python3
"""Bring released upgrade sections over from the product's `UPGRADE.md`.

An upgrade note is written at PR time in `mcp-hangar`, next to the change that
motivates it, headed `## Next`. The release job gives it a version. This brings
the versioned result here, which is where readers find it.

Replacing the by-hand copy that did this before. That copy happened **once**:
the 2.7.0 session-id note exists in both files, promoted here and still headed
`Next` there, and 2.8.0 and 2.9.0 never arrived at all -- two releases that
removed public API, with changelog entries pointing at an upgrade note that did
not exist (mcp-hangar/mcp-hangar#983).

**Prepend only, never replace.** `upgrade.md` is the published history and holds
versions the product's file never had -- 1.3.0 through 2.6.0, written before the
`## Next` convention existed. Anything already here is left exactly as it is,
including a section this repo has since edited. The product's copy is the
*source for new sections*, not the authority over old ones.

Usage:
    python scripts/sync_upgrade_guide.py [--source PATH] [--docs PATH] [--check]

`--check` reports what would be added and exits 1 if anything would, for asking
"are we behind" without writing. Exit 0 = nothing to add (or added), 1 = drift
under `--check`, 2 = bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"^## Upgrade to (\d+)\.(\d+)\.(\d+)", re.M)
HEADING_RE = re.compile(r"^## ", re.M)
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def resolve_source(arg: str | None) -> Path:
    raw = arg or os.getenv("MCP_HANGAR_SRC") or "../mcp-hangar"
    path = Path(raw).expanduser().resolve()
    if not (path / "UPGRADE.md").is_file():
        sys.exit(f"error: '{path}' has no UPGRADE.md. Pass --source or set MCP_HANGAR_SRC.")
    return path


def sections(text: str) -> dict[tuple[int, int, int], str]:
    """Version -> that section's whole text, `## Upgrade to X.Y.Z` sections only."""
    out: dict[tuple[int, int, int], str] = {}
    for match in SECTION_RE.finditer(text):
        following = HEADING_RE.search(text, match.end())
        end = following.start() if following else len(text)
        out[tuple(int(g) for g in match.groups())] = text[match.start() : end].rstrip("\n") + "\n"
    return out


def insert_point(text: str) -> int:
    """Above the newest existing section, below the frontmatter and the intro."""
    first = HEADING_RE.search(text)
    if first:
        return first.start()
    frontmatter = FRONTMATTER_RE.match(text)
    return frontmatter.end() if frontmatter else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Path to the mcp-hangar source repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--check", action="store_true", help="Report drift, write nothing.")
    args = parser.parse_args()

    source = resolve_source(args.source)
    guide = Path(args.docs).expanduser().resolve() / "upgrade.md"
    if not guide.is_file():
        sys.exit(f"error: {guide} not found.")

    upstream = sections((source / "UPGRADE.md").read_text(encoding="utf-8"))
    text = guide.read_text(encoding="utf-8")
    have = sections(text)

    missing = sorted(set(upstream) - set(have), reverse=True)

    if not missing:
        print(f"OK: upgrade.md carries every released section ({len(have)} of them).")
        return 0

    names = ", ".join(".".join(str(p) for p in v) for v in missing)
    if args.check:
        print(f"DRIFT: upgrade.md is missing {len(missing)} section(s): {names}")
        return 1

    cut = insert_point(text)
    added = "\n".join(upstream[v] for v in missing)
    guide.write_text(text[:cut] + added + "\n" + text[cut:], encoding="utf-8")

    print(f"Added {len(missing)} section(s) to upgrade.md: {names}")
    print("\nRead them before merging. They were written per-PR against the product,")
    print("and this repo's guide is what a reader actually gets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
