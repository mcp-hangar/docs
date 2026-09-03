#!/usr/bin/env python3
"""Check that every `config.yaml` block in the docs uses keys Hangar reads.

This gate was blocked for a while, and the reason is worth keeping: the obvious
implementation -- push each block through Hangar's `load_configuration()` --
validates nothing. `config.yaml` had no schema, so the loader accepted
`commandd: [python]`, `idle_tt1_s: 60` and a whole misspelled `authh:` section
without complaint (mcp-hangar/mcp-hangar#982). A gate built on it would have
been green over a documented typo.

The product grew a schema, so this consumes that instead of keeping a key
allowlist here. An allowlist in this repository would be a copy of
`server/config.py` living one repository away from the code it describes, and
it would drift silently -- a drifted copy either misses new keys or rejects
them, and both make the gate worse than nothing.

`config_schema.py` imports only `os` and `typing`, so it is loaded from the
source checkout by path. Installing the product to lint prose is a large hammer,
and the docs CI job deliberately does not do it.

Only blocks that look like a Hangar configuration are checked: a mapping with a
`mcp_servers` key, or with a known top-level section. A Kubernetes manifest is
`check_manifests.py`'s business and a random yaml fragment is nobody's.

Usage:
    python scripts/check_config.py [--source PATH] [--docs PATH] [--quiet]

Exit code 0 = clean, 1 = a key nothing reads, 2 = bad invocation.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path
from types import ModuleType

import yaml

EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}
BLOCK_RE = re.compile(r"^```ya?ml\n(.*?)^```", re.S | re.M)

# Fewer than this means the extraction broke, not that the docs lost their
# configuration examples. There are ~70 blocks today across guides and cookbook.
MIN_EXPECTED_BLOCKS = 40


def resolve_source(arg: str | None) -> Path:
    raw = arg or os.getenv("MCP_HANGAR_SRC") or "../mcp-hangar"
    path = Path(raw).expanduser().resolve()
    if not (path / "src" / "mcp_hangar").is_dir():
        sys.exit(
            f"error: '{path}' does not look like the mcp-hangar source repo "
            f"(missing src/mcp_hangar/). Pass --source or set MCP_HANGAR_SRC."
        )
    return path


def load_schema(source: Path) -> ModuleType:
    """Import `config_schema.py` from the checkout without installing anything."""
    path = source / "src" / "mcp_hangar" / "server" / "config_schema.py"
    if not path.is_file():
        sys.exit(
            f"error: {path} not found. The config schema landed in "
            f"mcp-hangar/mcp-hangar#984; a checkout older than that cannot be checked."
        )
    spec = importlib.util.spec_from_file_location("mcp_hangar_config_schema", path)
    if spec is None or spec.loader is None:
        sys.exit(f"error: could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROPOSED_ADR_RE = re.compile(r"^\*\*Status:\*\*\s*Proposed\s*$", re.M)


def is_proposed_adr(doc: Path, text: str) -> bool:
    """A Proposed ADR may name a key the shipped schema does not have yet.

    That is what proposing it means: the record is written before the code, so
    the gate would refuse every ADR that decides anything about configuration.
    The exemption ends at Accepted -- an ADR whose decision has shipped is
    checked like any other document, so a key that was renamed between the
    proposal and the implementation still gets caught.
    """
    return doc.parent.name == "adr" and bool(PROPOSED_ADR_RE.search(text))


def iter_docs(root: Path):
    for f in sorted(root.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def looks_like_hangar_config(doc: object, sections: set[str]) -> bool:
    if not isinstance(doc, dict) or "apiVersion" in doc:
        return False
    return "mcp_servers" in doc or bool(sections & set(doc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Path to the mcp-hangar source repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    source = resolve_source(args.source)
    schema = load_schema(source)
    sections = set(schema.SECTIONS)
    root = Path(args.docs).expanduser().resolve()

    problems: list[str] = []
    checked = 0
    skipped_proposals = 0

    for doc in iter_docs(root):
        rel = doc.relative_to(root)
        text = doc.read_text(encoding="utf-8", errors="ignore")
        if is_proposed_adr(doc, text):
            skipped_proposals += 1
            continue
        for match in BLOCK_RE.finditer(text):
            lineno = text[: match.start()].count("\n") + 1
            try:
                block = yaml.safe_load(match.group(1))
            except yaml.YAMLError:
                # A deliberate fragment, or a block with `...` in it. Not this
                # gate's business; `check_manifests.py` makes the same call.
                continue
            if not looks_like_hangar_config(block, sections):
                continue
            checked += 1
            for problem in schema.validate_config(block):
                problems.append(f"{rel}:{lineno}: {problem}")

    if not args.quiet:
        print(f"docs:   {root}")
        print(f"source: {source}")
        print(f"config blocks checked: {checked}")
        if skipped_proposals:
            print(f"proposed ADRs skipped: {skipped_proposals}")
        print()

    if checked < MIN_EXPECTED_BLOCKS:
        print(f"FAIL: found only {checked} config blocks.")
        print("The docs did not lose their examples -- the extraction in this script broke.")
        return 1

    if not problems:
        print(f"OK: all {checked} config blocks use keys Hangar reads.")
        return 0

    print(f"FAIL: {len(problems)} documented key(s) that nothing reads:\n")
    for problem in problems:
        print(f"  {problem}")
    print("\nA key Hangar does not read is kept and ignored, so a reader who copies")
    print("this block gets a setting that silently does not apply. Fix the spelling,")
    print("or the nesting -- `rate_limit` exists at the top level and under `auth`,")
    print("and they take different keys.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
