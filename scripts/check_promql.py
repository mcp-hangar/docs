#!/usr/bin/env python3
"""Check that every PromQL query in the docs is one Prometheus would accept.

`promtool` has no "parse this expression" mode, so each query is wrapped as a
recording rule and the whole set is handed to `promtool check rules` in one
pass. Rule names carry an index that maps back to the file and line the query
came from, so a failure names the doc rather than a rule number.

The count assertion is not defensive padding. `promtool check rules` answers
**"SUCCESS: 0 rules found"** for an empty file -- so if the extraction silently
yields nothing, promtool reports success and the gate has checked nothing. That
is not hypothetical: it is why the promtool gate in `helm-charts`
(mcp-hangar/helm-charts#144) compares a rendered rule count against its source
rather than trusting a green promtool.

A ```promql block holds several queries, and this repository writes them two
ways: the guides separate them by blank lines with a `#` comment above each,
while the runbooks put one whole query per line with nothing between. Splitting
on blank lines alone therefore merged the runbooks' queries and reported nine
real ones as broken. See `split_queries` for the rule that tells a new query
from the continuation of the previous one.

Usage:
    python scripts/check_promql.py [--docs PATH] [--promtool PATH] [--quiet]

Exit code 0 = clean, 1 = a query that does not parse, 2 = promtool missing.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}
BLOCK_RE = re.compile(r"^```promql\n(.*?)^```", re.S | re.M)

# Fewer than this means the extraction broke, not that the docs lost their
# queries. There are 14 blocks today across the guides and every runbook.
MIN_EXPECTED_QUERIES = 10


# A line that opens more brackets than it closes continues on the next one, and
# so does a line beginning with an infix operator or a closing bracket. Both
# shapes are in this repository: the guides wrap a ratio across two lines with a
# leading `/`, and the runbooks put one whole query per line with no blank line
# between them. Splitting on blank lines alone merged the runbooks' queries into
# one expression and reported nine real queries as broken.
CONTINUATION_RE = re.compile(r"^\s*([/*+\-]|or\b|and\b|unless\b|\))")


def split_queries(block: str) -> list[str]:
    queries: list[str] = []
    current: list[str] = []
    depth = 0
    for raw in block.splitlines():
        line = raw.split("#", 1)[0] if raw.strip().startswith("#") else raw
        if not line.strip():
            continue
        starts_new = current and depth <= 0 and not CONTINUATION_RE.match(line)
        if starts_new:
            queries.append("\n".join(current).strip())
            current = []
        current.append(line)
        depth += line.count("(") - line.count(")") + line.count("[") - line.count("]")
    if current:
        queries.append("\n".join(current).strip())
    return [q for q in queries if q]


def iter_docs(root: Path):
    for f in sorted(root.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def queries(root: Path) -> list[tuple[str, int, str]]:
    """(relative path, line of the fence, one query) for every query found."""
    out: list[tuple[str, int, str]] = []
    for doc in iter_docs(root):
        text = doc.read_text(encoding="utf-8", errors="ignore")
        rel = str(doc.relative_to(root))
        for m in BLOCK_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            for expr in split_queries(m.group(1)):
                out.append((rel, line, expr))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--promtool", default="promtool", help="promtool binary.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    promtool = shutil.which(args.promtool) or (args.promtool if Path(args.promtool).exists() else None)
    if not promtool:
        print(f"error: promtool not found ({args.promtool}). It ships in the Prometheus release tarball.")
        return 2

    root = Path(args.docs).expanduser().resolve()
    found = queries(root)

    if not args.quiet:
        print(f"docs: {root}")
        print(f"promql queries found: {len(found)}\n")

    if len(found) < MIN_EXPECTED_QUERIES:
        print(f"FAIL: found only {len(found)} PromQL queries.")
        print("The docs did not lose their queries -- the extraction in this script broke.")
        print("A green promtool over zero rules is the failure this check exists to prevent.")
        return 1

    rules = ["groups:", "  - name: docs", "    rules:"]
    for i, (_, _, expr) in enumerate(found):
        indented = "\n".join("          " + l for l in expr.splitlines())
        rules.append(f"      - record: docs:q{i}")
        rules.append("        expr: |")
        rules.append(indented)

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("\n".join(rules) + "\n")
        path = fh.name

    proc = subprocess.run([promtool, "check", "rules", path], capture_output=True, text=True)
    output = proc.stdout + proc.stderr

    if proc.returncode == 0:
        # Belt and braces: promtool says SUCCESS for an empty file, so confirm it
        # actually saw the rules we wrote rather than trusting the exit code.
        seen = re.search(r"SUCCESS:\s*(\d+)\s+rules found", output)
        if seen and int(seen.group(1)) != len(found):
            print(f"FAIL: wrote {len(found)} rules, promtool found {seen.group(1)}.")
            print(output.strip())
            return 1
        print(f"OK: all {len(found)} PromQL queries parse.")
        return 0

    print(f"FAIL: promtool rejected at least one of {len(found)} queries:\n")
    for line in output.splitlines():
        m = re.search(r'"docs:q(\d+)"', line)
        if m:
            rel, lineno, expr = found[int(m.group(1))]
            first = expr.splitlines()[0]
            print(f"  {rel}:{lineno}: {first[:80]}")
            print(f"    {line.strip()[:160]}")
        elif line.strip():
            print(f"  {line.strip()[:160]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
