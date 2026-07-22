# Egress Policy (MCPEgressPolicy)

Declarative, deny-by-default egress policy for MCP servers: control which upstreams a server may reach, which tool calls it may make, and what happens when the answer is no.

## Overview

`MCPEgressPolicy` is the policy layer above the binary registration switch. Registration (an `MCPServer` exists), default-deny egress, admission rejection of unregistered pods, and image-pin coupling answer *"may this server receive traffic at all?"* An egress policy answers the next question: *"which upstreams, which tool calls, with which arguments — and what happens on a violation?"*

Enforcement has two layers, applied together:

| Layer | Enforced by | Governs |
|-------|-------------|---------|
| **L3/L4** (network backstop) | operator → `NetworkPolicy` or `CiliumNetworkPolicy` | which upstream hosts/CIDRs the server's pods can reach |
| **L7** (semantics) | core, on connections Hangar proxies | which tool calls (by name) and which arguments are allowed |

The trust boundary is explicit: **a policy without the network backstop is a suggestion.** If a pod can bypass DNS and NetworkPolicy, it can bypass Hangar. The backstop is what makes the L7 policy enforcement rather than a recommendation. See [ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md) for the model and the alternatives that were rejected (no transparent TLS interception, no eBPF protocol parsing in v1).

## Prerequisites

- The operator, with the `MCPEgressPolicy` CRD installed (v0.13.0 shipped the enforcement roadmap; the `MCPEgressPolicy` reconciler ships in the release after it).
- The target namespace should be opted into egress enforcement with the label `mcp-hangar.io/enforce-egress=true`, so the namespace default-deny is in place and the backstop has something to build on.
- **For FQDN upstreams:** a cluster running **Cilium**. A vanilla `NetworkPolicy` cannot match on DNS names, so hostname upstreams are only enforceable under the Cilium flavor (see [Backstop flavors](#backstop-flavors)).
- **For L7 enforcement** (tool-call / argument rules): the operator must be run with `--hangar-url` pointing at the core, so it can deliver the compiled policy to the data plane. Without it, only the L3/L4 backstop is applied.

## A complete example

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata:
  name: gh-only
  namespace: prod
spec:
  mode: Enforce                 # Audit (default) observes; Enforce blocks
  targetRef:
    kind: MCPServer             # or MCPServerGroup
    name: srv
  defaultAction: Deny           # applied to tool names no rule matches
  upstreams:
    - name: github
      match:
        host: api.github.com    # FQDN -> needs the Cilium flavor
      tools:
        allow: ["get_*", "list_*"]
        requireApproval: ["create_*"]
      arguments:
        deny:
          secretPatterns: [aws-keys, jwt]
          maxPayloadBytes: 262144
```

Applied to a governed namespace on a Cilium cluster, the operator compiles this into a `CiliumNetworkPolicy` that allows DNS and egress only to `api.github.com`, and reports:

```
$ kubectl -n prod get mcpegresspolicy gh-only \
    -o jsonpath='{range .status.conditions[*]}{.type}={.status} ({.reason}){"\n"}{end}'
Compiled=True (Compiled)
BackstopApplied=True (BackstopApplied)
Degraded=False (NotDegraded)
```

A pod behind this policy reaches `api.github.com` (HTTP 200) but not any other host (connection times out), while DNS still resolves.

### Governing a group

`targetRef.kind: MCPServerGroup` applies one policy to every member of a group. The operator resolves the group's member servers and scopes the backstop to all of them (`mcp-hangar.io/provider In [members]`):

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata:
  name: web-egress
  namespace: prod
spec:
  mode: Enforce
  targetRef:
    kind: MCPServerGroup
    name: web-servers
  upstreams:
    - name: github
      match: {host: api.github.com}
      tools: {allow: ["get_*", "list_*"]}
```

### Deny everything

With `defaultAction: Deny` (the default) and no `upstreams`, the policy denies all egress except the always-permitted DNS/backstop paths — a locked-down server that can resolve names but reach no upstream:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata:
  name: lockdown
  namespace: prod
spec:
  mode: Enforce
  targetRef: {kind: MCPServer, name: srv}
  # no upstreams -> nothing is allowed out
```

## Spec reference

### Top level

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `Audit` \| `Enforce` | `Audit` | `Audit` observes violations; `Enforce` blocks. Audit-default gives a Gatekeeper-style adoption path. |
| `targetRef.kind` | `MCPServer` \| `MCPServerGroup` | — | What the policy attaches to. A group applies the policy to every member server. |
| `targetRef.name` | string | — | Referent name, resolved in the policy's namespace. |
| `defaultAction` | `Deny` \| `Allow` | `Deny` | Outcome for a tool name that no `upstreams[].tools` rule matches. |
| `upstreams[]` | list | — | The allow-list. With `defaultAction: Deny`, an empty list denies everything except the DNS/backstop paths. |
| `networkBackstop` | object | generate/Auto | Controls the generated L3/L4 backstop (below). |

### `upstreams[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Rule name, unique within the policy (enforced by a CEL rule). |
| `match.host` | string | Upstream host: an FQDN (needs Cilium), or a literal IP/CIDR (works under any CNI). |
| `match.toolSchemaDigestRef` | string | References an existing per-tenant tool-schema pin. |
| `match.imageDigest` | `required` \| `inherited` | How the target's image pin gates this upstream. |
| `match.issuers` | list | Restricts which token issuers may be brokered to this upstream. |
| `tools.allow` / `tools.deny` / `tools.requireApproval` | list of globs | Tool-name globs. Precedence: **deny > requireApproval > allow > defaultAction**. |
| `arguments.deny.secretPatterns` | list | Named secret-pattern groups to reject (below). |
| `arguments.deny.maxPayloadBytes` | integer | Reject tool-call argument payloads larger than this. |

### `networkBackstop`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `generate` | bool | `true` | Emit the L3/L4 backstop. `false` removes it (the policy then relies on the namespace default-deny alone). |
| `flavor` | `Auto` \| `Cilium` \| `Vanilla` | `Auto` | Backstop implementation. |

## Backstop flavors

The network backstop is what guarantees the data plane cannot be bypassed. The operator picks or is told a flavor:

- **`Vanilla`** — a standard `NetworkPolicy`: default-deny egress on the target's pods, allowing DNS plus any upstream whose `host` is a **literal IP/CIDR**. A vanilla `NetworkPolicy` cannot match on FQDNs, so hostname upstreams are **failed closed** (denied, never opened to "any destination") and surfaced as `Degraded/FQDNUpstreamsUnenforceable`.
- **`Cilium`** — a `CiliumNetworkPolicy` with `toFQDNs`, which **does** enforce hostname allow-lists. The DNS rule carries an L7 DNS-proxy rule so Cilium learns the resolved IPs and admits only traffic to the allow-listed names. CIDR upstreams become `toCIDR`.
- **`Auto`** (default) — Cilium if the `CiliumNetworkPolicy` CRD is installed, otherwise Vanilla.

If `Cilium` is requested on a cluster without the CRD, the operator applies the Vanilla floor and reports `Degraded/CiliumUnavailable` — it fails closed, never open.

## L7 semantics

The L7 half runs in the core, on the connections Hangar already proxies. It is **deterministic**: no ML, no heuristics to tune (full DLP and ML classification are explicit non-goals).

**Tool-call matching** resolves a tool name by glob, in precedence order:

1. `deny` — reject.
2. `requireApproval` — **fail closed**: the call is blocked pending out-of-band
   approval. This is a hard gate, not an interactive approval queue — routing a
   gated call into the interactive approval workflow is a follow-up (see
   [Limitations](#limitations-and-notes)).
3. `allow` — permit.
4. otherwise — the policy's `defaultAction`.

Globs are case-sensitive for determinism (`get_*` does not match `GET_user`).

**Argument scanning** rejects a tool call whose arguments contain a configured secret pattern or exceed `maxPayloadBytes`. A secret or oversized payload **denies the call even when the tool itself is allowed** — deny always wins. Arguments that cannot be serialized for inspection also fail closed.

**How the L7 policy is delivered.** The operator compiles the policy's per-upstream `tools`/`arguments` rules into a single per-server policy — the union of the upstreams' allow/deny/require-approval globs and secret-pattern groups, and the most restrictive (smallest) `maxPayloadBytes` — and pushes it to the core (requires `--hangar-url`). The core enforces it at the tool-invocation chokepoint: a denied call raises before it reaches the upstream; an approval-gated call is blocked pending approval. Deleting the policy clears it from the core.

### Secret-pattern groups

`secretPatterns` names groups; each maps to deterministic value-regexes shared with Hangar's output redactor, so what the redactor masks on the way out is what a policy refuses on the way in:

| Group | Detects |
|-------|---------|
| `aws-keys` | AWS access key IDs (`AKIA…`) |
| `jwt` | JSON Web Tokens (`eyJ….…`) |
| `pem-blocks` | PEM private-key blocks |
| `github-tokens` | GitHub PATs / OAuth / server / refresh tokens |
| `stripe-keys` | Stripe live/test/restricted keys |
| `slack-tokens` | Slack tokens (`xox…`) |
| `google-api-keys` | Google API keys (`AIza…`) |
| `bearer-tokens` | `Bearer …` credentials |
| `npm-tokens`, `pypi-tokens` | npm / PyPI tokens |

Unknown group names are ignored by the scanner (they are caught by CRD validation).

## Status conditions

| Condition | Meaning |
|-----------|---------|
| `Compiled` | The policy was structurally compiled. |
| `BackstopApplied` | The L3/L4 backstop is in place (`False` with `BackstopGenerationDisabled` when `generate: false`). |
| `Degraded` | An at-risk state: `FQDNUpstreamsUnenforceable` (FQDN upstreams under the Vanilla flavor), `CiliumUnavailable` (Cilium requested, CRD absent), or `TargetNotFound`. |

## Limitations and notes

- **L7 needs core integration.** The tool-call / argument rules are enforced only when the operator runs with `--hangar-url`; otherwise a policy applies its L3/L4 backstop but its L7 rules are not delivered.
- **FQDN enforcement requires Cilium.** Under other CNIs, list upstreams as CIDRs, or accept that hostname upstreams are denied (fail closed) and surfaced via `Degraded`.
- **L7 rules are merged per server.** Because the core enforces one policy per server (not per upstream connection), a policy's upstream `tools`/`arguments` rules are flattened together (see [above](#l7-semantics)). Scope host-specific tool rules with separate policies if you need them kept apart.
- **`requireApproval` currently fails closed** — a gated call is blocked pending out-of-band approval; routing it into the interactive approval queue is a follow-up.
- `toFQDNs` interacts with NodeLocal DNSCache; the operator's DNS-topology configuration (`ExtraDNSEgressPeers`) covers the same ground.

## See also

- [ADR-013: Egress Policy Enforcement Model](../adr/ADR-013-egress-policy-enforcement-model.md) — the enforcement model and rejected alternatives.
- [MCP Server Groups](MCP_SERVER_GROUPS.md) — the aggregation the group target will attach to.
- [OWASP MCP Top 10 coverage](../security/OWASP_MCP_TOP_10_COVERAGE.md) — how this maps to MCP09 and related controls.
