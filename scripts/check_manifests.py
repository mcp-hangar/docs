#!/usr/bin/env python3
"""Check that Kubernetes manifests in the docs use fields the operator honours.

The defect this exists for has already happened once, in the product's own
`examples/kubernetes/`: manifests teaching `kind: MCPProvider`, `v1alpha1`,
`idleTTL`, `healthCheck`, `circuitBreaker` and group `strategy`/`failover` --
every one of them removed from the CRD in the operator's honesty pass, every one
still being taught (mcp-hangar/mcp-hangar#928). The docs carry the same shape of
manifest and had the same absence of checking.

The schema is read from the operator repository's `config/crd/bases`, never from
a copy pasted into this one. A copied schema drifts, and a drifted schema is a
gate that approves the wrong thing.

Checked, per `mcp-hangar.io` manifest found in a ```yaml fence:
  * the kind exists in the CRDs
  * `apiVersion` names a version the CRD actually serves
  * every `spec` key exists in that version's schema
  * every key one level into `spec.capabilities` exists

Deliberately NOT checked: Kubernetes' own kinds (`Secret`, `ConfigMap`,
`Deployment`, ...) that share a fence with a Hangar manifest. Those are the API
server's schema, and `kubeconform` is the tool for that if it is ever wanted.

Usage:
    python scripts/check_manifests.py [--operator PATH] [--docs PATH] [--quiet]

Operator path resolution: --operator, $MCP_HANGAR_OPERATOR_SRC,
../mcp-hangar-operator.
Exit code 0 = clean, 1 = a field or version the CRD does not have, 2 = bad
invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

EXCLUDED_DOCS = {"CHANGELOG.md", "changelog.md"}
GROUP = "mcp-hangar.io"

FENCE_OPEN_RE = re.compile(r"^\s*```\s*(\w+)?")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

# Fewer CRDs than this means the schema load broke, not that the operator lost
# its API. MCPServer, MCPServerGroup, MCPDiscoverySource, MCPEgressPolicy.
MIN_EXPECTED_KINDS = 3


def resolve_operator(arg: str | None) -> Path:
    raw = arg or os.getenv("MCP_HANGAR_OPERATOR_SRC") or "../mcp-hangar-operator"
    path = Path(raw).expanduser().resolve()
    if not (path / "config" / "crd" / "bases").is_dir():
        sys.exit(
            f"error: '{path}' does not look like the mcp-hangar-operator repo "
            f"(missing config/crd/bases/). Pass --operator or set MCP_HANGAR_OPERATOR_SRC."
        )
    return path


def load_schemas(operator: Path) -> tuple[dict[str, dict[str, dict]], dict[str, str]]:
    """(kind -> version -> that version's `spec` properties, kind -> storage version)."""
    out: dict[str, dict[str, dict]] = {}
    storage: dict[str, str] = {}
    for f in sorted((operator / "config" / "crd" / "bases").glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not doc or doc.get("kind") != "CustomResourceDefinition":
            continue
        kind = doc["spec"]["names"]["kind"]
        for v in doc["spec"]["versions"]:
            spec = v.get("schema", {}).get("openAPIV3Schema", {}).get("properties", {}).get("spec", {})
            out.setdefault(kind, {})[v["name"]] = spec.get("properties", {})
            if v.get("storage"):
                storage[kind] = v["name"]
    return out, storage


def yaml_blocks(text: str):
    lang, buf, start = None, [], 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if lang is None:
            m = FENCE_OPEN_RE.match(line)
            if m:
                lang, buf, start = (m.group(1) or "").lower(), [], lineno
            continue
        if FENCE_CLOSE_RE.match(line):
            if lang in {"yaml", "yml"}:
                yield start, "\n".join(buf)
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
    parser.add_argument("--operator", help="Path to the mcp-hangar-operator repo.")
    parser.add_argument("--docs", default=".", help="Path to the docs repo root.")
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    args = parser.parse_args()

    operator = resolve_operator(args.operator)
    docs = Path(args.docs).expanduser().resolve()
    schemas, storage = load_schemas(operator)

    if len(schemas) < MIN_EXPECTED_KINDS:
        print(f"FAIL: loaded only {len(schemas)} CRD kind(s) ({sorted(schemas)}).")
        print("The operator did not lose its API -- the schema load in this script broke.")
        return 1

    problems: list[str] = []
    checked = 0

    for doc in iter_docs(docs):
        rel = doc.relative_to(docs)
        for lineno, block in yaml_blocks(doc.read_text(encoding="utf-8", errors="ignore")):
            try:
                found = list(yaml.safe_load_all(block))
            except yaml.YAMLError:
                # A fragment that is not whole YAML is not this gate's business;
                # the config gate (#219) is where partial blocks are decided.
                continue
            for manifest in found:
                if not isinstance(manifest, dict):
                    continue
                api = str(manifest.get("apiVersion", ""))
                if not api.startswith(GROUP + "/"):
                    continue
                where = f"{rel}:{lineno}"
                checked += 1
                kind = manifest.get("kind")
                version = api.split("/", 1)[1]
                if kind not in schemas:
                    problems.append(f"{where}: kind {kind!r} is not a CRD ({sorted(schemas)})")
                    continue
                if version not in schemas[kind]:
                    served = sorted(schemas[kind])
                    problems.append(f"{where}: {kind} has no version {version!r} (served: {served})")
                    continue
                # Served is not the same as current. `v1alpha1` is still served
                # for conversion, and a doc teaching it teaches the API the
                # honesty pass moved away from -- which is the defect
                # mcp-hangar/mcp-hangar#928 fixed in the product's own examples.
                if kind in storage and version != storage[kind]:
                    problems.append(
                        f"{where}: {kind} uses {version!r}; docs teach the storage version, {storage[kind]!r}"
                    )
                props = schemas[kind][version]
                spec = manifest.get("spec") or {}
                if not isinstance(spec, dict):
                    continue
                unknown = sorted(set(spec) - set(props))
                if unknown:
                    problems.append(f"{where}: {kind}.spec has {unknown} -- not in the {version} CRD")
                caps = spec.get("capabilities")
                cap_props = props.get("capabilities", {}).get("properties", {})
                if isinstance(caps, dict) and cap_props:
                    unknown_caps = sorted(set(caps) - set(cap_props))
                    if unknown_caps:
                        allowed = sorted(cap_props)
                        problems.append(
                            f"{where}: {kind}.spec.capabilities has {unknown_caps} -- allowed: {allowed}"
                        )

    if not args.quiet:
        print(f"docs:     {docs}")
        print(f"operator: {operator}")
        print(f"CRD kinds: {sorted(schemas)}")
        print(f"manifests checked: {checked}\n")

    if checked == 0:
        print(f"FAIL: no `{GROUP}` manifest found in any yaml block -- extraction is broken.")
        return 1

    if not problems:
        print(f"OK: all {checked} manifest(s) use fields the CRD defines.")
        return 0

    print(f"FAIL: {len(problems)} manifest problem(s):\n")
    for p in sorted(set(problems)):
        print(f"  {p}")
    print("\nThe operator is the deploy-time admission plane. Runtime behaviour it")
    print("does not own -- idle stop, circuit breaking, tool allow-lists, load")
    print("balancing -- belongs in Hangar's own config, not on these CRs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
