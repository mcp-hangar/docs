#!/usr/bin/env python3
"""Check that every relative link in the docs resolves -- file and anchor.

Separate from `validate_docs.py` on purpose: that one is a drift detector and
needs the `mcp-hangar` source tree for every check it makes. This one needs
nothing but the docs, so it runs in a fraction of a second, locally, without
cloning the product.

What it checks:
  * `[text](path)`            -- the target file exists
  * `[text](path#anchor)`     -- and, for a Markdown target, some heading in it
                                 produces that anchor

Deliberately NOT checked:
  * external URLs -- liveness is flaky, rate-limited, and needs the network
  * bare `#fragment` links into the *same* page. The renderer also emits ids for
    things that are not headings, so the heading set is not the full anchor set
    for a self-link. Cross-file anchors are checked because a wrong one there is
    almost always a moved or renamed section.

Anchors are slugged the way GitHub and `rehype-slug` do it, which is what both
this repo's Markdown viewer and the website use: lowercase, drop anything that
is not a word character, space or hyphen, then spaces to hyphens. Repeats get
`-1`, `-2`, ... in document order.

Usage:
    python scripts/check_links.py [--docs PATH] [--quiet]

Exit code 0 = clean, 1 = broken link(s).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The changelog is an immutable historical record: it links to sections and
# files as they were at the time. Same exclusion `validate_docs.py` makes, for
# the same reason.
EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}

LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def slug(text: str) -> str:
    """GitHub-flavoured heading slug.

    Inline markup is stripped first: a heading written ``## The `auth` block``
    renders as ``the-auth-block``, and leaving the backticks in produces an
    anchor nothing links to.
    """
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # `*` and `~` only: an underscore is a word character and survives slugging,
    # so stripping it here turned `startup_checks` into `startupchecks` and
    # reported eight live anchors as broken.
    text = re.sub(r"[*~]", "", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text.strip())


def anchors(path: Path) -> set[str]:
    """Every anchor the headings of *path* produce, duplicates numbered."""
    seen: dict[str, int] = {}
    out: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        text = m.group(2)
        # An explicit `{#custom-id}` wins over the slug, which is the point of
        # writing one. Missing this reported a live anchor as broken:
        # `### \`hangar_sources\` (async) {#hangar_sources}` slugs to
        # `hangar_sources-async` and is linked as `#hangar_sources`.
        explicit = re.search(r"\{#([A-Za-z0-9_-]+)\}\s*$", text)
        if explicit:
            out.add(explicit.group(1).lower())
            continue
        base = slug(text)
        if not base:
            continue
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


def iter_docs(root: Path):
    for f in sorted(root.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    root = Path(args.docs).expanduser().resolve()
    cache: dict[Path, set[str]] = {}
    problems: list[str] = []
    checked = 0
    scanned = 0

    for doc in iter_docs(root):
        scanned += 1
        rel = doc.relative_to(root)
        for lineno, line in enumerate(doc.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for target in LINK_RE.findall(line):
                if target.startswith(("http://", "https://", "mailto:", "#", "<")):
                    continue
                checked += 1
                path_part, _, anchor = target.partition("#")
                if not path_part:
                    continue
                resolved = (doc.parent / path_part).resolve()
                if not resolved.exists():
                    problems.append(f"{rel}:{lineno}: no such file -> {target}")
                    continue
                if anchor and resolved.suffix == ".md":
                    if resolved not in cache:
                        cache[resolved] = anchors(resolved)
                    if anchor.lower() not in cache[resolved]:
                        problems.append(f"{rel}:{lineno}: no such heading -> {target}")

    if not args.quiet:
        print(f"docs: {root}")
        print(f"scanned {scanned} markdown files, {checked} relative links\n")

    # A run that checked nothing is not a passing run. If the extraction breaks,
    # this says so instead of reporting success over an empty set -- the failure
    # shape that makes a gate look green while guarding nothing.
    if checked == 0:
        print("FAIL: no relative links were found at all -- the extraction is broken.")
        return 1

    if not problems:
        print(f"OK: all {checked} relative links resolve.")
        return 0

    print(f"FAIL: {len(problems)} broken link(s):\n")
    for p in problems:
        print(f"  {p}")
    print("\nA link to a section names its heading, slugged: lowercase, punctuation")
    print("dropped, spaces to hyphens. Rename the heading or the link, not both.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
