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
Then the quickstart's steps, each in a fresh home: `init` over a client that
lists the stub writes `flat` with its tool beside the pins; `add git` writes the
entry the quickstart shows, which is refused until it has `flat: []`; and
`init --skip-test` writes `flat: []` on a server it installs and leaves a
client's server in the client. Every `text` fence quoting the front-door
refusal must match what `config check` prints, up to the page's `...`.

Usage:
    python scripts/check_config_published.py --venv PATH [--docs PATH]
    python scripts/check_config_published.py --selftest

Exit code 0 = every block and every step behaved as the docs say, 1 = not,
2 = bad invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_config import BLOCK_RE, is_skipped, iter_docs  # noqa: E402

#: There are ~85 complete configs today. Fewer than this means the extraction
#: broke, not that the docs lost their examples.
MIN_EXPECTED_BLOCKS = 60

REFUSED_RE = re.compile(r"^\s*<!--\s*config-check:\s*refused\s+(.+?)\s*-->\s*$")

#: A `text` fence, indented when it sits in a list item.
TEXT_FENCE_RE = re.compile(r"^[ \t]*```text\n(.*?)^[ \t]*```", re.S | re.M)

#: What marks a quote of the refusal a front door without `flat` prints.
REFUSAL_PHRASE = "has not chosen which of its tools are projected"

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
    quoted = (
        "- It refuses:\n\n  ```text\n  mcp_servers.pay is served on a front door (tool_access.mode: front_door)"
        " and has not chosen which of its tools are projected under their own\n  names. ...\n  ```\n\n"
        "```text\nsomething else\n```\n"
    )
    assert list(quoted_refusals(quoted)) == [
        (
            3,
            "pay",
            "mcp_servers.pay is served on a front door (tool_access.mode: front_door) and has not chosen"
            " which of its tools are projected under their own names.",
        )
    ], "an indented quote is found, cut at its `...`, and other text fences are not"
    page = "```bash\nmcp-hangar add git --no-reload\n```\n\nProse.\n\n```yaml\n  git:\n    mode: subprocess\n```\n"
    assert quickstart_git_entry(page) == {"mode": "subprocess"}, "the entry after `add git` is read, dedented"
    print("OK: selftest")
    return 0


class Runner:
    def __init__(self, venv: Path, home: Path) -> None:
        self.binary = venv / "bin" / "mcp-hangar"
        self.python = venv / "bin" / "python"
        self.env = {**os.environ, **ENV_EXTRA, "HOME": str(home)}
        self.env.pop("MCP_CONFIG", None)

        # The home is also the working directory, so no `./config.yaml` of the
        # caller's is picked up by a command that falls back to it.
        self.home = home

    def __call__(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [str(self.binary), *args],
            capture_output=True,
            text=True,
            env=self.env,
            cwd=self.home,
            stdin=subprocess.DEVNULL,
            timeout=180,
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


def quoted_refusals(text: str):
    """Yield `(lineno, server, quote)` for every `text` fence quoting the front-door refusal.

    The quote ends where the page cut it short with `...`; what is left of it
    must be in the output word for word, with the page's server name.
    """
    for match in TEXT_FENCE_RE.finditer(text):
        quote = flat(match.group(1))
        if REFUSAL_PHRASE not in quote:
            continue
        name = re.match(r"mcp_servers\.([\w-]+) ", quote)
        if name:
            lineno = text[: match.start()].count("\n") + 1
            yield lineno, name.group(1), quote.removesuffix("...").rstrip()


def check_quoted_refusals(root: Path, run: Runner, work: Path) -> list[str]:
    """Each page that quotes the front-door refusal quotes what the wheel prints."""
    server = work / "server.py"
    server.write_text(STUB_SERVER)
    problems: list[str] = []
    quotes = 0
    for doc in iter_docs(root):
        rel = doc.relative_to(root)
        if rel.parts[0] == "adr":
            continue
        for lineno, name, quote in quoted_refusals(doc.read_text(encoding="utf-8", errors="ignore")):
            quotes += 1
            config = {
                "tool_access": {"mode": "front_door"},
                "mcp_servers": {name: {"mode": "subprocess", "command": [str(run.python), str(server)]}},
            }
            path = work / f"refusal-{quotes}.yaml"
            path.write_text(yaml.safe_dump(config))
            code, output = run("config", "check", str(path))
            if code != 1 or quote not in output:
                problems.append(
                    f"{rel}:{lineno}: the quoted refusal is not what config check prints (exit {code}): {output}"
                )
    if not quotes:
        problems.append("no page quotes the front-door refusal; the extraction broke")
    return problems


def walk_quickstart(root: Path, venv: Path, work: Path) -> list[str]:
    """The quickstart's step 3 and "Adding more MCP servers", and the reference's `--skip-test`, in a fresh home each."""
    server = work / "server.py"
    server.write_text(STUB_SERVER)
    problems: list[str] = []

    def init(name: str, *args: str, client: bool = True) -> tuple[Runner, dict, Path]:
        home = work / name
        home.mkdir()
        run = Runner(venv, home)
        if client:
            client_config = {"mcpServers": {"notes": {"command": str(run.python), "args": [str(server)]}}}
            (home / ".claude.json").write_text(json.dumps(client_config))
        code, output = run("init", "-y", *args)
        written = home / ".config" / "mcp-hangar" / "config.yaml"
        if code != 0 or not written.is_file():
            problems.append(f"init {' '.join(args)} failed (exit {code}): {output}")
            return run, {}, written
        return run, yaml.safe_load(written.read_text()).get("mcp_servers") or {}, written

    # Step 3: a client's server moves in with its pins, and `flat` names every tool the test saw.
    run, servers, written = init("init", "--client", "claude-code")
    projection = (servers.get("notes") or {}).get("tool_projection") or {}
    if projection.get("flat") != ["list_notes"] or "list_notes" not in (projection.get("pins") or {}):
        problems.append(f"init did not write flat and pins for the tool its test saw: {projection!r}")

    # "Adding more MCP servers": `add` writes the page's entry without `flat`, the file
    # is refused until the entry has one, and `flat: []` makes it load.
    if servers:
        documented = quickstart_git_entry((root / "getting-started" / "quickstart.md").read_text())
        code, output = run("add", "git", "--no-reload", "-y")
        config = yaml.safe_load(written.read_text())
        added = dict(config["mcp_servers"].get("git") or {})
        if code != 0 or added != {k: v for k, v in documented.items() if k != "tool_projection"}:
            problems.append(
                f"add git did not write the quickstart's entry (exit {code}): {added!r}: {output}"
            )
        code, output = run("config", "check", str(written))
        if code != 1 or "must be chosen explicitly" not in output:
            problems.append(f"config check did not refuse the entry add wrote (exit {code}): {output}")
        config["mcp_servers"]["git"] = {**added, "tool_projection": documented.get("tool_projection")}
        written.write_text(yaml.safe_dump(config))
        code, output = run("config", "check", str(written))
        if code != 0:
            problems.append(
                f"config check refused git with the quickstart's `flat: []` (exit {code}): {output}"
            )

    # `--skip-test` takes no pins and writes `flat: []` on a server it installs...
    _, servers, _ = init(
        "skip-test-servers", "--skip-test", "--servers", "memory", "--skip-clients", client=False
    )
    if (servers.get("memory") or {}).get("tool_projection") != {"flat": []}:
        problems.append(f"init --skip-test did not write `flat: []` and no pins: {servers.get('memory')!r}")
    # ...and leaves a client's server in the client, because moving one needs its first start.
    run, servers, _ = init("skip-test-client", "--skip-test", "--client", "claude-code")
    kept = json.loads((run.home / ".claude.json").read_text()).get("mcpServers") or {}
    if "notes" in servers or "notes" not in kept:
        problems.append(
            f"init --skip-test moved a client's server: config {sorted(servers)}, client {sorted(kept)}"
        )
    return problems


def quickstart_git_entry(page: str) -> dict:
    """The `git` entry the quickstart shows right after `mcp-hangar add git`."""
    after = page[page.index("mcp-hangar add git") :]
    match = BLOCK_RE.search(after)
    if not match:
        return {}
    return (yaml.safe_load(textwrap.dedent(match.group(1))) or {}).get("git") or {}


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
        problems += check_quoted_refusals(root, run, work)
        problems += walk_quickstart(root, venv, work)

    if problems:
        print(f"FAIL: {len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  {problem}\n")
        return 1
    print("OK: every block behaves on the published wheel as its page says, and so do the flat steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
