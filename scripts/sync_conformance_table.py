#!/usr/bin/env python3
"""Splice core's generated conformance pass table into reference/conformance.md.

Core's `MCP Conformance` workflow assembles the pass table from each run's own
results and uploads it as the `conformance-pass-table` artifact. The
`sync-conformance` workflow downloads the newest one from a run on core's
`main` and calls this, which rewrites only the block between the
`generated: conformance-pass-table` markers. Nothing in the block is typed by
hand: it is the artifact, under one line saying which run produced it.

Refuses to write, leaving the page as it was, when the markers are missing or
the table does not hold all six legs in core's order: the egress server and
the client on 2026-07-28 and 2025-11-25, then the front_door server on both
revisions.

Usage: sync_conformance_table.py TABLE_MD RUN_URL HEAD_SHA [PAGE]
       sync_conformance_table.py --selftest
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LEGS = (
    "Server, 2026-07-28",
    "Server, 2025-11-25",
    "Client, 2026-07-28",
    "Client, 2025-11-25",
    "Server, front_door, 2026-07-28",
    "Server, front_door, 2025-11-25",
)
BLOCK = re.compile(
    r"(<!-- BEGIN generated: conformance-pass-table.*?-->\n).*?(\n<!-- END generated: conformance-pass-table -->)",
    re.S,
)


def splice(page: str, table: str, run_url: str, head_sha: str) -> str:
    if not BLOCK.search(page):
        raise ValueError("conformance-pass-table markers not found")
    missing = [leg for leg in LEGS if f"### {leg}\n" not in table]
    if missing:
        raise ValueError("the pass table is missing legs: " + ", ".join(missing))
    order = [table.index(f"### {leg}\n") for leg in LEGS]
    if order != sorted(order):
        raise ValueError("the pass table's legs are not in core's order: " + ", ".join(LEGS))
    body = f"Generated from [this run]({run_url}) of core at `{head_sha[:12]}` on `main`.\n\n" + table.strip("\n")
    return BLOCK.sub(lambda m: m.group(1) + body + m.group(2), page)


def selftest() -> int:
    page = "intro\n<!-- BEGIN generated: conformance-pass-table x -->\nold\n<!-- END generated: conformance-pass-table -->\nend\n"
    table = "".join(f"### {leg}\n\n| a |\n" for leg in LEGS)
    out = splice(page, table, "https://example.invalid/run/1", "f3d946c2" + "0" * 32)
    assert "old" not in out and out.startswith("intro\n") and out.endswith("end\n"), out
    assert "Generated from [this run](https://example.invalid/run/1) of core at `f3d946c20000`" in out, out
    assert splice(out, table, "https://example.invalid/run/2", "a" * 40).count("### Server, 2026-07-28") == 1
    four = "".join(f"### {leg}\n\n| a |\n" for leg in LEGS[:4])
    swapped = "".join(f"### {leg}\n\n| a |\n" for leg in (*LEGS[4:], *LEGS[:4]))
    bad = (
        (page.replace("BEGIN", "START"), table),
        (page, table.replace("### Client, 2025-11-25", "")),
        (page, table.replace("### Server, front_door, 2025-11-25", "")),
        (page, four),
        (page, swapped),
    )
    for bad_page, bad_table in bad:
        try:
            splice(bad_page, bad_table, "u", "s")
        except ValueError:
            continue
        raise AssertionError("a page without markers, or a table missing a leg or out of order, was written")
    print("sync_conformance_table selftest: ok")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    target = Path(argv[4] if len(argv) > 4 else "reference/conformance.md")
    try:
        updated = splice(target.read_text(), Path(argv[1]).read_text(), argv[2], argv[3])
    except ValueError as e:
        print(f"::error::{e}; refusing to write {target}", file=sys.stderr)
        return 1
    target.write_text(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
