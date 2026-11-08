#!/usr/bin/env python3
"""Run a walkthrough page's commands as a reader would, and check what they print.

The cluster walkthrough this replaces was verified by reading it: it
port-forwarded a port the chart does not listen on, piped an event stream into
`jq` and expected an unauthenticated call to pass (docs#462). This runs the
page instead, so a command that only works on the author's machine fails here.

The page marks what to run with HTML comments, which a rendered page hides:

- `<!-- ci:walkthrough -->` above a ```bash fence: the block is run. Every
  ```bash fence on the page must carry it, so no command a reader is shown
  goes unrun.
- `<!-- ci:file NAME -->` above a fence: its content is written to NAME in the
  working directory first, as the page tells the reader to save it.
- `<!-- ci:expect TEXT -->` after a run block: that block's output must
  contain TEXT.

The blocks are joined into one `bash -e -o pipefail` script, run in an empty
directory: one shell, as a reader has it, so a variable or function from one
block is there in the next. A failing command stops the run where it fails.

Usage:
    python scripts/run_kind_walkthrough.py PAGE [--require-expect TEXT ...] [--print]

`--require-expect` fails the run unless the page itself expects TEXT, so the
assertion a job relies on cannot be deleted from the page unnoticed. `--print`
writes the generated script to stdout and runs nothing.

Exit code 0 = every block ran and every expectation held, 1 = otherwise,
2 = a page this cannot read.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN = re.compile(r"^<!-- ci:walkthrough -->$")
FILE = re.compile(r"^<!-- ci:file ([A-Za-z0-9._-]+) -->$")
EXPECT = re.compile(r"^<!-- ci:expect (.+?) -->$")
FENCE = re.compile(r"^```(\w*)\s*$")
SENTINEL = "@@walkthrough-step {}@@"


class PageError(Exception):
    pass


def parse(text: str) -> list[tuple[str, str, str]]:
    """The page's steps in reading order: ("file", name, body), ("run", "", body), ("expect", "", text)."""
    steps: list[tuple[str, str, str]] = []
    pending: tuple[str, str] | None = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if RUN.match(line):
            pending = ("run", "")
        elif m := FILE.match(line):
            pending = ("file", m.group(1))
        elif m := EXPECT.match(line):
            if not any(kind == "run" for kind, _, _ in steps):
                raise PageError(
                    f"line {i + 1}: ci:expect before any ci:walkthrough block"
                )
            steps.append(("expect", "", m.group(1)))
        elif m := FENCE.match(lines[i]):
            end = next(
                (j for j in range(i + 1, len(lines)) if lines[j].rstrip() == "```"),
                None,
            )
            if end is None:
                raise PageError(f"line {i + 1}: fence never closes")
            body = "\n".join(lines[i + 1 : end]) + "\n"
            if pending is not None:
                steps.append((pending[0], pending[1], body))
            elif m.group(1) == "bash":
                raise PageError(
                    f"line {i + 1}: a bash block without <!-- ci:walkthrough --> would go unrun"
                )
            pending = None
            i = end
        i += 1
    if pending is not None:
        raise PageError("a ci: marker has no fence below it")
    return steps


def script_for(steps: list[tuple[str, str, str]]) -> str:
    parts = []
    run = 0
    for kind, name, body in steps:
        if kind == "file":
            parts.append(
                f"cat > {name} <<'__WALKTHROUGH_EOF__'\n{body}__WALKTHROUGH_EOF__\n"
            )
        elif kind == "run":
            run += 1
            parts.append(f"printf '\\n%s\\n' '{SENTINEL.format(run)}'\n{body}")
    return "\n".join(parts)


def outputs_by_step(log: str) -> dict[int, str]:
    found: dict[int, str] = {}
    pieces = re.split(r"^@@walkthrough-step (\d+)@@$", log, flags=re.MULTILINE)
    for number, chunk in zip(pieces[1::2], pieces[2::2]):
        found[int(number)] = chunk
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("page", type=Path)
    parser.add_argument("--require-expect", action="append", default=[])
    parser.add_argument("--print", action="store_true", dest="print_only")
    args = parser.parse_args(argv)

    try:
        steps = parse(args.page.read_text(encoding="utf-8"))
    except (OSError, PageError) as e:
        print(f"{args.page}: {e}", file=sys.stderr)
        return 2
    expects: list[tuple[int, str]] = []
    run = 0
    for kind, _, body in steps:
        if kind == "run":
            run += 1
        elif kind == "expect":
            expects.append((run, body))
    if run == 0:
        print(
            f"{args.page}: no <!-- ci:walkthrough --> block, nothing to run",
            file=sys.stderr,
        )
        return 2
    missing = [
        t for t in args.require_expect if not any(t in text for _, text in expects)
    ]
    if missing:
        print(f"{args.page}: the page no longer expects {missing}", file=sys.stderr)
        return 1

    script = script_for(steps)
    if args.print_only:
        sys.stdout.write(script)
        return 0

    with tempfile.TemporaryDirectory(prefix="walkthrough-") as work:
        proc = subprocess.Popen(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=work,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        log = []
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.append(line)
        code = proc.wait()

    if code != 0:
        print(f"\nFAIL: the walkthrough stopped with exit code {code}", file=sys.stderr)
        return 1
    outputs = outputs_by_step("".join(log))
    failed = [(n, text) for n, text in expects if text not in outputs.get(n, "")]
    for n, text in failed:
        print(f"FAIL: block {n} did not print {text!r}", file=sys.stderr)
    if failed:
        return 1
    print(f"\nOK: {run} blocks ran, {len(expects)} expectations held.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
