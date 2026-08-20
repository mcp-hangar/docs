#!/usr/bin/env python3
"""Make a stale "current version" claim a build error instead of a discovery.

Two mechanisms, one gate.

**Currency claims.** A line that says something is *current*, *latest*, or true
*today* and names a version is a promise with a shelf life. The page keeps
reading plausibly long after it stops being true, which is why this class is
found by readers rather than by review: `architecture/OVERVIEW.md` advertised
core `v1.6.0` and operator `v0.14.0` three releases after both moved.

A historical statement is not a currency claim and is not flagged. "Fixed as of
2.5.0", "since 2.6.0", "shipped in 2.0.0" are true forever, and a gate that
cannot tell the two apart gets switched off.

**The token.** A file that legitimately needs to name the current version
carries:

    <!-- verified-against: 2.9.0 -->

which does two things: it permits the currency claims in that file, and it fails
the build once the released version moves more than one minor ahead. The token
is an acknowledgement that a human read the page -- so it is deliberately not
bumped automatically. A bot that advances it turns the gate into a formality.

**Upgrade coverage.** The two mechanisms above check what a page *says*. Neither
notices a page that says nothing, which is how `upgrade.md` came to stop at
2.7.0 while 2.9.0 was the released version -- two releases, both removing public
API, both with a changelog entry reading "see `UPGRADE.md`" and nothing to see.
So the released minor must have a `## Upgrade to X.Y...` section. A release with
no migration steps is a one-line section saying so, which is a cheaper thing to
write than this paragraph is to read.

The released version is read from the product's `pyproject.toml` in the source
checkout, so this needs no network.

Usage:
    python scripts/check_freshness.py [--source PATH] [--docs PATH] [--quiet]

Exit code 0 = clean, 1 = an unbacked currency claim or a stale token.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}

# Present tense only. `today` is matched separately so "as of today" still reads
# as historical via the HISTORICAL_RE guard below.
CURRENCY_RE = re.compile(r"\b(current|currently|latest)\b|\btoday\b", re.I)
HISTORICAL_RE = re.compile(r"\b(as of|since|used to|before|was|were|fixed in|shipped in)\b", re.I)
VERSION_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")
TOKEN_RE = re.compile(r"<!--\s*verified-against:\s*(\d+)\.(\d+)(?:\.(\d+))?\s*-->")
# A fence DELIMITER is a line that is nothing but the fence, plus an optional
# one-word info string. Matching any ``` -- even `r"^```.*?^```"` -- is not
# enough: prose that mentions fence syntax ("wraps every query in a ```promql
# fence") can wrap so the backticks land in column 0, and this very page has
# two. Each one is an unpaired delimiter that pairs every fence below it with
# the wrong neighbour, so the stripper removes the prose BETWEEN blocks and
# leaves the code in -- the exact inversion of what it is for.
FENCE_LINE_RE = re.compile(r"^```[\w+-]*[ \t]*$")
GENERATED_RE = re.compile(r"<!--\s*BEGIN generated.*?<!--\s*END generated[^>]*-->", re.S)

# How far the released version may move past a token before the page must be
# re-read. One minor: a patch is a fix, a minor is new surface.
MAX_MINOR_DRIFT = 1

UPGRADE_DOC = "upgrade.md"
UPGRADE_HEADING_RE = re.compile(r"^#{2,3}\s+Upgrade to (\d+)\.(\d+)", re.M)


def upgrade_gap(root: Path, major: int, minor: int) -> str | None:
    """The released minor has no section in the upgrade guide, or a reason it does."""
    doc = root / UPGRADE_DOC
    if not doc.is_file():
        return f"{UPGRADE_DOC} is missing -- the upgrade guide is where a removal is explained."
    covered = {(int(a), int(b)) for a, b in UPGRADE_HEADING_RE.findall(doc.read_text(encoding="utf-8"))}
    if not covered:
        return f"{UPGRADE_DOC} has no `## Upgrade to X.Y` heading at all -- the parse here broke."
    if (major, minor) in covered:
        return None
    newest = max(covered)
    return (
        f"{UPGRADE_DOC}: no section for the released {major}.{minor}; newest is "
        f"{newest[0]}.{newest[1]}. Add one -- 'nothing to do' is a valid section."
    )


def resolve_source(arg: str | None) -> Path:
    raw = arg or os.getenv("MCP_HANGAR_SRC") or "../mcp-hangar"
    path = Path(raw).expanduser().resolve()
    if not (path / "pyproject.toml").is_file():
        sys.exit(f"error: '{path}' has no pyproject.toml. Pass --source or set MCP_HANGAR_SRC.")
    return path


def released_version(source: Path) -> tuple[int, int, int]:
    text = (source / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)', text, re.M)
    if not m:
        sys.exit("error: could not read `version` from the product's pyproject.toml.")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def prose(text: str) -> str:
    """The part of a page a human wrote as claims: no code, no generated regions.

    Generated regions carry versions by construction and are rewritten by their
    own job, so a claim inside one is not a human's to keep fresh. Fenced blocks
    are illustrations -- including, on the page documenting this gate, an
    illustration of the freshness token itself.
    """
    out, inside = [], False
    for line in GENERATED_RE.sub("", text).splitlines():
        if FENCE_LINE_RE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def file_token(text: str) -> "re.Match[str] | None":
    """The page's freshness token, read from prose only.

    Read from :func:`prose` rather than the raw text, so a page may show the
    token's syntax without thereby claiming to carry one.
    """
    return TOKEN_RE.search(prose(text))


def iter_docs(root: Path):
    for f in sorted(root.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def selftest() -> int:
    """Pin what `prose` must and must not treat as code.

    Every regression here is silent. A fenced illustration counted as a token
    makes a page demand a re-read nobody can perform; prose mistaken for a
    fence hides a real currency claim from the scan; and dropping the stripping
    makes a real token stop registering, at which point the gate stops gating.
    """
    fenced = "# P\n\nExample:\n\n```markdown\n<!-- verified-against: 2.11.0 -->\n```\n"
    assert file_token(fenced) is None, "a fenced example must not count as a token"

    real = "<!-- verified-against: 2.11.0 -->\n\n# P\n\nThe current version is 2.11.0.\n"
    assert file_token(real) is not None, "a token in prose must still count"

    generated = "<!-- BEGIN generated x -->\n<!-- verified-against: 2.11.0 -->\n<!-- END generated x -->\n"
    assert file_token(generated) is None, "a token inside a generated region is not a human's"

    # Prose that mentions fence syntax, wrapped so the backticks start a line.
    # Treating it as a delimiter inverts the pairing of every fence below it.
    wrapped = (
        "Validates every manifest in a\n"
        "```yaml fence against the CRDs -- the kind, every `spec` key.\n"
        "\n"
        "```bash\n"
        "run --this\n"
        "```\n"
        "\n"
        "The current release is 9.9.9.\n"
    )
    kept = prose(wrapped)
    assert "run --this" not in kept, "a real fenced block must be stripped"
    assert "The current release is 9.9.9." in kept, "prose after a wrapped mention must survive"
    assert "```yaml fence against" in kept, "prose that merely mentions a fence is not a fence"

    print("selftest: ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Path to the mcp-hangar source repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    parser.add_argument(
        "--selftest", action="store_true", help="Check what counts as code, a token and a claim."
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    source = resolve_source(args.source)
    root = Path(args.docs).expanduser().resolve()
    rel_major, rel_minor, rel_patch = released_version(source)

    unbacked: list[str] = []
    stale: list[str] = []
    tokened = 0

    for doc in iter_docs(root):
        rel = doc.relative_to(root)
        text = doc.read_text(encoding="utf-8", errors="ignore")

        token = file_token(text)
        if token:
            tokened += 1
            major, minor = int(token.group(1)), int(token.group(2))
            drift = (rel_major - major) * 1000 + (rel_minor - minor)
            if drift > MAX_MINOR_DRIFT:
                stale.append(
                    f"{rel}: verified-against {major}.{minor}, released is "
                    f"{rel_major}.{rel_minor}.{rel_patch} -- re-read the page and bump the token"
                )
            continue

        for lineno, line in enumerate(prose(text).splitlines(), 1):
            if HISTORICAL_RE.search(line):
                continue
            if CURRENCY_RE.search(line) and VERSION_RE.search(line):
                unbacked.append(f"{rel}:{lineno}: {line.strip()[:90]}")

    gap = upgrade_gap(root, rel_major, rel_minor)

    if not args.quiet:
        print(f"docs:     {root}")
        print(f"released: {rel_major}.{rel_minor}.{rel_patch}")
        print(f"files carrying a freshness token: {tokened}\n")

    if not unbacked and not stale and not gap:
        print("OK: no unbacked currency claim, no stale freshness token, upgrade guide covers the release.")
        return 0

    if gap:
        print(f"FAIL: {gap}\n")

    if stale:
        print(f"FAIL: {len(stale)} stale freshness token(s):\n")
        for s in stale:
            print(f"  {s}")
        print()

    if unbacked:
        print(f"FAIL: {len(unbacked)} version claim(s) that nothing keeps fresh:\n")
        for u in unbacked:
            print(f"  {u}")
        print()
        print("Either stop naming the version -- point at the generated table, or at")
        print("what `pip install` resolves to -- or add a token to the file:")
        print(f"    <!-- verified-against: {rel_major}.{rel_minor}.{rel_patch} -->")
        print("A statement about the past ('since 2.6.0', 'fixed in 2.5.0') is not a")
        print("currency claim and is never flagged.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
