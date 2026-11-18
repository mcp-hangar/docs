#!/usr/bin/env python3
"""Run every complete config block in the docs through the published wheel.

`check_config.py` reads key names from a source checkout. It cannot see a value
the gateway refuses, and 2.37.0 showed what that costs: nine front-door
examples, two of them in the quickstart, had valid keys and no
`tool_projection.flat`, so the gateway they describe refused to start
(mcp-hangar/mcp-hangar#1374). This gate installs nothing itself. The workflow
installs `mcp-hangar` from PyPI into a virtualenv, as a reader would, and this
asks that install's own `mcp-hangar config check` about each block. That runs
the key schema, the process-wide checks the boot runs (`flat` among them) and
the `mcp_servers` build, and starts nothing.

Which fences it reads: a ```yaml fence whose top level is a mapping with
`mcp_servers` in it. That is a whole `config.yaml`; a fragment (one section, one
server entry) is not, and `config check` would refuse it for what it leaves out.
Every such block must be accepted, so a new example is checked without anyone
marking it. `adr/` is left out: a decision record shows a shape with elided
values (`sha256:9f2c...`), and an Accepted ADR cannot be edited to satisfy a
gate; `check_config.py` still checks its keys. Two markers, on the line above
the fence:

- `<!-- config-check: skip -->`, `check_config.py`'s marker for a removed key
  shown in an upgrade note, skips the block here too.
- `<!-- config-check: refused TEXT -->` says the block is shown because the
  gateway refuses it. `config check` must refuse it, and its output must
  contain TEXT, so the page's claim about why is checked as well.

It also runs the commands the configuration reference gives for filling
`flat`, against a stub stdio upstream: with `flat: []` the file is accepted
and `pin` prints the server's tools; `pin --write` writes `pins` and leaves
`flat` alone; without `flat`, both `config check` and `pin` refuse the file.

Usage:
    python scripts/check_config_published.py --venv PATH [--docs PATH]
    python scripts/check_config_published.py --selftest

Exit code 0 = every block and every step behaved as the docs say, 1 = not,
2 = bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_config import BLOCK_RE, is_skipped, iter_docs  # noqa: E402

#: There are ~85 complete configs today. Fewer than this means the extraction
#: broke, not that the docs lost their examples.
MIN_EXPECTED_BLOCKS = 60

REFUSED_RE = re.compile(r"^\s*<!--\s*config-check:\s*refused\s+(.+?)\s*-->\s*$")

#: `config check` prints through rich, which wraps at the terminal width.
ENV_EXTRA = {"COLUMNS": "400", "NO_COLOR": "1", "TERM": "dumb"}

STUB_SERVER = '''\
try:  # SDK v2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # SDK v1
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("notes")


@mcp.tool(name="list_notes")
def list_notes() -> list[str]:
    """List the notes."""
    return []


if __name__ == "__main__":
    mcp.run()
'''


def refused_text(text: str, start: int) -> str | None:
    """The TEXT of a `refused` marker above the fence at `start`, as `is_skipped` reads its marker."""
    for line in reversed(text[:start].splitlines()[-2:]):
        match = REFUSED_RE.match(line)
        if match:
            return match.group(1)
        if line.strip():
            return None
    return None


def complete_configs(text: str):
    """Yield `(lineno, body, refused)` for every whole `config.yaml` fence not marked `skip`."""
    for match in BLOCK_RE.finditer(text):
        if is_skipped(text, match.start()):
            continue
        body = match.group(1)
        try:
            block = yaml.safe_load(body)
        except yaml.YAMLError:
            continue
        if isinstance(block, dict) and isinstance(block.get("mcp_servers"), dict):
            lineno = text[: match.start()].count("\n") + 1
            yield lineno, body, refused_text(text, match.start())


def flat(output: str) -> str:
    return " ".join(output.split())


def selftest() -> int:
    page = (
        "```yaml\nmcp_servers:\n  a: {mode: remote}\n```\n\n"
        "```yaml\ntool_access:\n  mode: front_door\n```\n\n"
        "<!-- config-check: skip -->\n\n```yaml\nmcp_servers:\n  b: {}\n```\n\n"
        "<!-- config-check: refused must be chosen -->\n\n```yaml\nmcp_servers:\n  c: {}\n```\n\n"
        "```yaml\nmcp_servers:\n  d: {}\n```\n\n"
        "<!-- config-check: refused far away -->\n\nProse.\n\n```yaml\nmcp_servers:\n  e: {}\n```\n"
    )
    got = [
        (yaml.safe_load(body)["mcp_servers"].popitem()[0], refused)
        for _, body, refused in complete_configs(page)
    ]
    assert got[0] == ("a", None), "a whole config is checked without a marker"
    assert "b" not in dict(got), "a skip-marked fence is not checked"
    assert len(got) == 4, f"a fragment is not a whole config: {got}"
    assert got[1] == ("c", "must be chosen"), "a refused marker carries its expected text"
    assert got[2] == ("d", None), "the refused marker covers one fence, not the next"
    assert got[3] == ("e", None), "prose between the marker and the fence ends it"
    assert flat("a\n  b   c\n") == "a b c"
    print("OK: selftest")
    return 0


class Runner:
    def __init__(self, venv: Path, home: Path) -> None:
        self.binary = venv / "bin" / "mcp-hangar"
        self.python = venv / "bin" / "python"
        self.env = {**os.environ, **ENV_EXTRA, "HOME": str(home)}
        self.env.pop("MCP_CONFIG", None)

    def __call__(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [str(self.binary), *args], capture_output=True, text=True, env=self.env, timeout=120
        )
        return result.returncode, flat(result.stdout + result.stderr)


def check_blocks(root: Path, run: Runner, work: Path) -> tuple[int, list[str]]:
    problems: list[str] = []
    checked = 0
    for doc in iter_docs(root):
        rel = doc.relative_to(root)
        if rel.parts[0] == "adr":
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for lineno, body, refused in complete_configs(text):
            checked += 1
            path = work / f"block-{checked}.yaml"
            path.write_text(body)
            code, output = run("config", "check", str(path))
            if refused is None and code != 0:
                problems.append(f"{rel}:{lineno}: refused by the published wheel: {output}")
            elif refused is not None and code != 1:
                problems.append(f"{rel}:{lineno}: marked refused, but config check exited {code}: {output}")
            elif refused is not None and flat(refused) not in output:
                problems.append(f"{rel}:{lineno}: refused, but not with {refused!r}: {output}")
    return checked, problems


def walk_fill_the_list(run: Runner, work: Path) -> list[str]:
    """The reference's "To fill the list" steps, in its order."""
    server = work / "server.py"
    server.write_text(STUB_SERVER)
    config = {
        "tool_access": {"mode": "front_door"},
        "mcp_servers": {
            "notes": {
                "mode": "subprocess",
                "command": [str(run.python), str(server)],
                "tool_projection": {"flat": []},
            }
        },
    }
    path = work / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    problems: list[str] = []

    code, output = run("config", "check", str(path))
    if code != 0:
        problems.append(f"config check refused `flat: []`: {output}")
    code, output = run("pin", "--config", str(path), "--quiet")
    if code != 0 or "list_notes" not in output:
        problems.append(f"pin with `flat: []` did not print the server's tool (exit {code}): {output}")
    code, output = run("pin", "--config", str(path), "--quiet", "--write")
    written = yaml.safe_load(path.read_text())["mcp_servers"]["notes"].get("tool_projection", {})
    if code != 0 or "list_notes" not in (written.get("pins") or {}):
        problems.append(f"pin --write wrote no pin for list_notes (exit {code}): {output}")
    if written.get("flat") != []:
        problems.append(f"pin --write changed flat: {written.get('flat')!r}")

    del config["mcp_servers"]["notes"]["tool_projection"]
    path.write_text(yaml.safe_dump(config))
    for args in (("config", "check", str(path)), ("pin", "--config", str(path), "--quiet")):
        code, output = run(*args)
        if code == 0 or "must be chosen explicitly" not in output:
            problems.append(
                f"`mcp-hangar {args[0]}` did not refuse a front door without flat (exit {code}): {output}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--venv", help="Virtualenv with the published mcp-hangar installed.")
    parser.add_argument("--selftest", action="store_true", help="Check which fences count as configuration.")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.venv:
        parser.error("--venv is required")
    venv = Path(args.venv).expanduser().resolve()
    if not (venv / "bin" / "mcp-hangar").is_file():
        print(f"no mcp-hangar in {venv}/bin", file=sys.stderr)
        return 2
    root = Path(args.docs).expanduser().resolve()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        run = Runner(venv, work)
        _, version = run("--version")
        print(f"published wheel: {version}")
        checked, problems = check_blocks(root, run, work)
        print(f"complete config blocks checked: {checked}")
        if checked < MIN_EXPECTED_BLOCKS:
            print(f"FAIL: found only {checked}. The extraction in this script broke, not the docs.")
            return 1
        problems += walk_fill_the_list(run, work)

    if problems:
        print(f"FAIL: {len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  {problem}\n")
        return 1
    print("OK: every block behaves on the published wheel as its page says, and so do the flat steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
