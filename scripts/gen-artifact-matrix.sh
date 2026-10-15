#!/usr/bin/env bash
# Regenerate the "Released artifacts" table in operations/RELEASE_COMPATIBILITY.md
# from the GHCR registry — the versions, digests, and chart appVersions are read
# live, not hand-maintained (they drifted three times before this existed).
#
# It also regenerates the "Chart release history" block: one row per published
# chart version with its appVersion and kubeVersion, read from the charts.
#
# Needs: gh (auth), crane, helm. Idempotent: rewrites only the blocks between the
# `<!-- BEGIN/END generated: ... -->` markers; if nothing changed,
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

# --- Chart release history -------------------------------------------------
# Every published chart version, newest first, so a chart release can never be
# missing from the page. The newest version read back from the registry must be
# in the table, or nothing is written.
chart_rows() {
  local chart="$1" versions
  versions="$(crane ls "$ORG/charts/$chart" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -rV)"
  require "$versions" "$chart versions"
  printf '%s\n' "$versions" | xargs -P 8 -I{} sh -c '
    meta="$(helm show chart "oci://$1/charts/$2" --version "$3")" || exit 1
    app="$(printf "%s\n" "$meta" | awk "/^appVersion:/{gsub(/[\"\047]/,\"\"); print \$2}")"
    kube="$(printf "%s\n" "$meta" | awk "/^kubeVersion:/{gsub(/[\"\047]/,\"\"); print \$2}")"
    printf "%s|%s|%s\n" "$3" "$app" "$kube"' _ "$ORG" "$chart" {} | sort -t'|' -k1,1rV
}

history_table() {
  local chart="$1" rows
  rows="$(chart_rows "$chart")"
  printf '%s\n' "$rows" | head -1 | grep -q "^$2|" \
    || { echo "::error::newest $chart $2 is missing from the history — refusing to write" >&2; exit 1; }
  printf '| Chart version | appVersion | kubeVersion |\n| --- | --- | --- |\n'
  printf '%s\n' "$rows" | awk -F'|' '{printf "| `%s` | `%s` | `%s` |\n", $1, $2, $3}'
}

CORE_HISTORY="$(history_table mcp-hangar "$cc_v")"
OP_HISTORY="$(history_table mcp-hangar-operator "$co_v")"
HISTORY="$(printf '**Chart `charts/mcp-hangar`**\n\n%s\n\n**Chart `charts/mcp-hangar-operator`**\n\n%s' "$CORE_HISTORY" "$OP_HISTORY")"

HISTORY="$HISTORY" python3 - "$FILE" <<'PY'
import os, re, sys
f = sys.argv[1]
s = open(f).read()
pat = re.compile(r"(<!-- BEGIN generated: chart-release-history.*?-->\n).*?(\n<!-- END generated: chart-release-history -->)", re.S)
if not pat.search(s):
    sys.exit("::error::chart-release-history markers not found in " + f)
open(f, "w").write(pat.sub(lambda m: m.group(1) + os.environ["HISTORY"] + m.group(2), s))
PY

echo "Regenerated chart release history."
