#!/usr/bin/env python3
"""Check that every `mcp-hangar` command the docs tell a reader to run exists.

Reads the command set out of the product's CLI source rather than importing it:
the docs CI job checks `mcp-hangar` out but does not install it, and installing
the product to lint prose is a large hammer for a small question. The tradeoff
is that this parses registration calls, so a change in how commands are
registered would stop finding them -- which is why the run FAILS when it finds
implausibly few, instead of silently approving everything.

Extraction is from ```bash fences only, and this is the whole difficulty. A
naive `mcp-hangar\\s+(\\w+)` over the full text of the docs reports sixteen
phantom subcommands -- `mcp-hangar resource`, `mcp-hangar spec`,
`mcp-hangar kubectl`, `mcp-hangar pip` -- every one of them prose or a YAML
fragment that happens to follow the product name. A gate that noisy is turned
off within a week, so the command must sit where a command sits: at the start of
a line, or after a shell operator.

Usage:
    python scripts/check_cli.py [--source PATH] [--docs PATH] [--quiet]

Source path resolution order: --source, $MCP_HANGAR_SRC, ../mcp-hangar.
Exit code 0 = clean, 1 = a command the CLI does not have, 2 = bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}

# `app.command(name="status")` / `app.add_typer(init.app, name="init")` in the
# composition module, and `@app.command(name="bootstrap-admin")` inside a group.
REGISTER_RE = re.compile(r"(?:app\.command|app\.add_typer)\([^)]*?name=[\"']([a-z][a-z0-9-]*)[\"']", re.S)

FENCE_OPEN_RE = re.compile(r"^\s*```\s*(\w+)?")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

# A command position: line start, or after a prompt, pipe, `&&`, `;`, or sudo.
# `$(...)` and backtick substitution count too -- they run the thing.
INVOCATION_RE = re.compile(
    r"(?:^|[|;&]\s*|\$\(\s*|`\s*|\bsudo\s+|^\s*\$\s+)\s*mcp-hangar\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?",
    re.M,
)

# Fewer registered commands than this means the parse stopped working, not that
# the CLI shrank. `status add remove serve init completion auth` is the floor.
MIN_EXPECTED_COMMANDS = 6


def resolve_source(arg: str | None) -> Path:
    raw = arg or os.getenv("MCP_HANGAR_SRC") or "../mcp-hangar"
    path = Path(raw).expanduser().resolve()
    if not (path / "src" / "mcp_hangar").is_dir():
        sys.exit(
            f"error: '{path}' does not look like the mcp-hangar source repo "
            f"(missing src/mcp_hangar/). Pass --source or set MCP_HANGAR_SRC."
        )
    return path


def command_set(source: Path) -> tuple[set[str], set[tuple[str, str]]]:
    """Top-level command names, and (group, subcommand) pairs."""
    cli_dir = source / "src" / "mcp_hangar" / "server" / "cli"
    main = cli_dir / "main.py"
    top = set(REGISTER_RE.findall(main.read_text(encoding="utf-8", errors="ignore"))) if main.exists() else set()

    pairs: set[tuple[str, str]] = set()
    for module in sorted((cli_dir / "commands").glob("*.py")):
        group = module.stem
        if group not in top:
            continue
        for sub in REGISTER_RE.findall(module.read_text(encoding="utf-8", errors="ignore")):
            pairs.add((group, sub))
    return top, pairs


def bash_blocks(text: str):
    """Yield the body of every ```bash / ```sh / ```shell fence."""
    lang, buf = None, []
    for line in text.splitlines():
        if lang is None:
            m = FENCE_OPEN_RE.match(line)
            if m:
                lang = (m.group(1) or "").lower()
                buf = []
            continue
        if FENCE_CLOSE_RE.match(line):
            if lang in {"bash", "sh", "shell", "console"}:
                yield "\n".join(buf)
            lang, buf = None, []
            continue
        buf.append(line)


def iter_docs(root: Path):
    for f in sorted(root.rglob("*.md")):
        if any(seg in {".git", "node_modules"} for seg in f.parts):
            continue
        if f.name in EXCLUDED_DOCS:
            continue
        yield f


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Path to the mcp-hangar source repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    source = resolve_source(args.source)
    docs = Path(args.docs).expanduser().resolve()
    top, pairs = command_set(source)
    groups = {g for g, _ in pairs}

    if len(top) < MIN_EXPECTED_COMMANDS:
        print(f"FAIL: found only {len(top)} registered commands ({sorted(top)}).")
        print("The CLI did not shrink -- the registration parse in this script stopped working.")
        return 1

    problems: list[str] = []
    cited = 0
    for doc in iter_docs(docs):
        rel = doc.relative_to(docs)
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for block in bash_blocks(text):
            for cmd, sub in INVOCATION_RE.findall(block):
                cited += 1
                if cmd not in top:
                    problems.append(f"{rel}: `mcp-hangar {cmd}` is not a command")
                elif sub and cmd in groups and (cmd, sub) not in pairs:
                    known = sorted(s for g, s in pairs if g == cmd)
                    problems.append(f"{rel}: `mcp-hangar {cmd} {sub}` -- {cmd} has {known}")

    if not args.quiet:
        print(f"docs:   {docs}")
        print(f"source: {source}")
        print(f"commands: {sorted(top)}")
        print(f"cited in bash blocks: {cited}\n")

    if cited == 0:
        print("FAIL: no `mcp-hangar` invocation found in any bash block -- extraction is broken.")
        return 1

    if not problems:
        print(f"OK: all {cited} CLI invocations name a real command.")
        return 0

    print(f"FAIL: {len(problems)} invocation(s) name something the CLI does not have:\n")
    for p in sorted(set(problems)):
        print(f"  {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
