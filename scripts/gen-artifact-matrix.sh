#!/usr/bin/env bash
# Regenerate the "Released artifacts" table in operations/RELEASE_COMPATIBILITY.md
# from the GHCR registry — the versions, digests, and chart appVersions are read
# live, not hand-maintained (they drifted three times before this existed).
#
# Needs: gh (auth), crane, helm. Idempotent: rewrites only the block between the
# `<!-- BEGIN/END generated: released-artifacts -->` markers; if nothing changed,
# the file is byte-identical and the caller opens no PR.
set -euo pipefail

FILE="${1:-operations/RELEASE_COMPATIBILITY.md}"
ORG="ghcr.io/mcp-hangar"

latest_semver() { grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1; }
require() { [ -n "$1" ] || { echo "::error::empty value for $2 — refusing to write a broken table" >&2; exit 1; }; }

core_v="$(gh release view -R mcp-hangar/mcp-hangar --json tagName -q .tagName | sed 's/^v//')"
op_v="$(gh release view -R mcp-hangar/mcp-hangar-operator --json tagName -q .tagName | sed 's/^v//')"
cc_v="$(crane ls "$ORG/charts/mcp-hangar" | latest_semver)"
co_v="$(crane ls "$ORG/charts/mcp-hangar-operator" | latest_semver)"
for pair in "core_v:$core_v" "op_v:$op_v" "cc_v:$cc_v" "co_v:$co_v"; do require "${pair#*:}" "${pair%%:*}"; done

core_d="$(crane digest "$ORG/mcp-hangar:$core_v")"
op_d="$(crane digest "$ORG/mcp-hangar-operator:$op_v")"
cc_d="$(crane digest "$ORG/charts/mcp-hangar:$cc_v")"
co_d="$(crane digest "$ORG/charts/mcp-hangar-operator:$co_v")"
cc_app="$(helm show chart "oci://$ORG/charts/mcp-hangar" --version "$cc_v" | awk '/^appVersion:/{print $2}')"
co_app="$(helm show chart "oci://$ORG/charts/mcp-hangar-operator" --version "$co_v" | awk '/^appVersion:/{print $2}')"
for pair in "core_d:$core_d" "cc_d:$cc_d" "cc_app:$cc_app" "co_app:$co_app"; do require "${pair#*:}" "${pair%%:*}"; done

TABLE="$(cat <<EOF
| Artifact | Version | Digest | Signed |
| --- | --- | --- | --- |
| Core image (\`$ORG/mcp-hangar\`) | \`$core_v\` | \`$core_d\` | ✅ |
| Operator image (\`$ORG/mcp-hangar-operator\`) | \`$op_v\` | \`$op_d\` | ✅ |
| Chart \`charts/mcp-hangar\` (appVersion \`$cc_app\`) | \`$cc_v\` | \`$cc_d\` | ✅ |
| Chart \`charts/mcp-hangar-operator\` (appVersion \`$co_app\`) | \`$co_v\` | \`$co_d\` | ✅ |
EOF
)"

TABLE="$TABLE" python3 - "$FILE" <<'PY'
import os, re, sys
f = sys.argv[1]
table = os.environ["TABLE"]
s = open(f).read()
pat = re.compile(r"(<!-- BEGIN generated: released-artifacts.*?-->\n).*?(\n<!-- END generated: released-artifacts -->)", re.S)
if not pat.search(s):
    sys.exit("::error::generated-artifacts markers not found in " + f)
open(f, "w").write(pat.sub(lambda m: m.group(1) + table + m.group(2), s))
PY

echo "Regenerated released-artifacts table: core $core_v, operator $op_v, charts $cc_v/$co_v."
