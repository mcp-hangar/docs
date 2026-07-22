# 24 -- Constrain Outbound Calls with the L7 Egress Policy Language

> **Prerequisite:** [11 -- Discovery: Kubernetes](11-discovery-kubernetes.md)
> **You will need:** The operator with the `MCPEgressPolicy` CRD installed, a
> namespace opted into egress enforcement (`mcp-hangar.io/enforce-egress=true`),
> the operator run with `--hangar-url` (for the L7 half), and **Cilium** if any
> upstream is an FQDN. See the [Egress Policy guide](../guides/EGRESS_POLICY.md)
> for the full prerequisites and trust model.
> **Time:** Read first, then plan -- this is a policy-language reference, not a
> 20-minute run
> **Adds:** A declarative, deny-by-default `MCPEgressPolicy` that controls which
> upstreams a server may reach, which tool calls it may make, and what happens
> when a call carries a secret or an oversized payload

## The Problem

Registration answers *"may this server receive traffic at all?"* It does not
answer the question that actually bounds a compromised or misbehaving provider:
*which upstreams, which tool calls, with which arguments -- and what happens when
the answer is no.* Without that layer, a registered server that gets popped can
still call any tool it exposes, exfiltrate a secret in a tool argument, or reach
any host it likes.

`MCPEgressPolicy` is the declarative policy language above the binary
registration switch. It is **deny-by-default**: you list the upstreams a server
may reach and the tool calls it may make, and everything else is refused.

### This is *not* `tool_access.mode: egress`

Two very different things share the word "egress." Do not confuse them:

| | `tool_access.mode: egress` | `MCPEgressPolicy` (this recipe) |
|---|---|---|
| Direction | **Inbound** -- how Hangar treats the *callers in front of it* | **Outbound** -- what a server may do to its *upstreams* |
| What it is | A topology/trust mode (the default; trusted internal callers see the full `hangar_*` meta-API) -- see [Front-Door Mode](../guides/FRONT_DOOR.md) | A Kubernetes CRD compiled and enforced by the operator + core |
| Governs | Client-facing tool projection and caller trust | Upstream hosts, tool-call globs, and argument content |

`tool_access.mode: egress` is a client-facing posture. `MCPEgressPolicy` is an
outbound enforcement policy. They are orthogonal and can both be in effect at
once.

## How It Enforces (two layers)

Enforcement is two layers applied together (see
[ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md)):

| Layer | Enforced by | Governs |
|-------|-------------|---------|
| **L3/L4** (network backstop) | operator → `NetworkPolicy` / `CiliumNetworkPolicy` | which upstream hosts/CIDRs the pods can reach |
| **L7** (semantics) | core, on the connections Hangar proxies | which tool calls (by name) and which arguments are allowed |

The trust boundary is explicit: **a policy without the network backstop is a
suggestion.** If a pod can bypass DNS and NetworkPolicy, it can bypass Hangar.
The L7 half is only delivered when the operator runs with `--hangar-url`;
otherwise only the L3/L4 backstop applies.

## The Config

A complete policy. Every field below mirrors the
[Egress Policy guide](../guides/EGRESS_POLICY.md) spec reference.

```yaml
# egress-policy.yaml -- Recipe 24: deny-by-default L7 egress policy
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata:
  name: gh-only
  namespace: prod                 # namespace must carry mcp-hangar.io/enforce-egress=true
spec:
  mode: Enforce                   # Audit (default) observes; Enforce blocks
  targetRef:
    kind: MCPServer               # or MCPServerGroup (applies to every member)
    name: srv
  defaultAction: Deny             # deny-by-default: outcome for any tool no rule matches
  upstreams:
    - name: github
      match:
        host: api.github.com      # FQDN -> requires the Cilium backstop flavor
      tools:
        allow: ["get_*", "list_*"]        # glob allow-list
        deny: ["*_admin"]                 # deny wins over everything
        requireApproval: ["create_*"]     # FAIL-CLOSED (see below)
      arguments:
        deny:
          secretPatterns: [aws-keys, jwt, github-tokens]  # reject calls carrying these
          maxPayloadBytes: 262144                          # reject oversized argument payloads
  networkBackstop:
    generate: true                # emit the L3/L4 backstop
    flavor: Auto                  # Auto | Cilium | Vanilla
```

### Deny everything

`defaultAction: Deny` with no `upstreams` is a locked-down server -- it can
resolve DNS but reach no upstream:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata: {name: lockdown, namespace: prod}
spec:
  mode: Enforce
  targetRef: {kind: MCPServer, name: srv}
  # no upstreams -> nothing is allowed out
```

## The Policy Language

### Tool-call matching (glob, precedence order)

A tool name is resolved by glob in **precedence order** -- the first match wins:

1. `deny` — reject.
2. `requireApproval` — **fail closed** (blocked pending out-of-band approval).
3. `allow` — permit.
4. otherwise — the policy's `defaultAction` (`Deny` by default).

Globs are **case-sensitive** for determinism (`get_*` does not match `GET_user`).

> **`requireApproval` fails closed -- it is not an approval queue.** A
> `requireApproval` match today **blocks** the call pending out-of-band
> approval. It is a hard gate, not an interactive/HITL approval workflow --
> wiring a gated call into an interactive approval queue is an explicit
> follow-up. Treat `requireApproval` as "deny unless separately approved," never
> as "prompt an operator to approve inline."

### Argument scanning

A tool call is rejected -- **even when the tool name is allowed** -- if its
arguments contain a configured secret pattern or exceed `maxPayloadBytes`. Deny
always wins. Arguments that cannot be serialized for inspection also fail closed.

`secretPatterns` names deterministic value-regex groups (no ML, no heuristics),
shared with Hangar's output redactor -- what the redactor masks on the way out is
what a policy refuses on the way in:

| Group | Detects |
|-------|---------|
| `aws-keys` | AWS access key IDs (`AKIA…`) |
| `jwt` | JSON Web Tokens |
| `pem-blocks` | PEM private-key blocks |
| `github-tokens` | GitHub PATs / OAuth / server / refresh tokens |
| `stripe-keys` | Stripe live/test/restricted keys |
| `slack-tokens` | Slack tokens (`xox…`) |
| `google-api-keys` | Google API keys (`AIza…`) |
| `bearer-tokens` | `Bearer …` credentials |
| `npm-tokens`, `pypi-tokens` | npm / PyPI tokens |

## Try It

1. Apply the policy to a governed namespace and confirm it compiled:

   ```bash
   kubectl apply -f egress-policy.yaml
   kubectl -n prod get mcpegresspolicy gh-only \
     -o jsonpath='{range .status.conditions[*]}{.type}={.status} ({.reason}){"\n"}{end}'
   ```

   Expected -- compiled, backstop in place, not degraded:

   ```text
   Compiled=True (Compiled)
   BackstopApplied=True (BackstopApplied)
   Degraded=False (NotDegraded)
   ```

2. Prove the network backstop. From a pod behind the policy, the allow-listed
   host answers and any other host times out, while DNS still resolves:

   ```bash
   # allowed upstream -> reachable
   kubectl -n prod exec deploy/srv -- curl -sS -o /dev/null -w "%{http_code}\n" https://api.github.com   # 200-ish
   # any other host -> connection times out
   kubectl -n prod exec deploy/srv -- curl -sS --max-time 5 https://example.com ; echo "exit=$?"          # non-zero
   ```

3. Prove the L7 half (requires the operator running with `--hangar-url`). A
   tool call that is *allowed by name* but carries a secret in its arguments is
   still refused at the invocation chokepoint, before it reaches the upstream --
   deny wins over allow.

## What Just Happened

The operator compiles the policy's per-upstream `tools`/`arguments` rules into a
single per-server policy -- the union of the upstreams' allow/deny/require-approval
globs and secret-pattern groups, and the **most restrictive (smallest)**
`maxPayloadBytes` -- and pushes it to the core over the same channel that already
feeds routing config (this needs `--hangar-url`). The same reconcile emits the
L3/L4 backstop:

- **`Vanilla`** — a standard `NetworkPolicy`: default-deny egress, DNS allowed,
  plus any upstream whose `host` is a literal **IP/CIDR**. FQDN upstreams are
  **failed closed** (denied, never opened to "any destination") and surfaced as
  `Degraded/FQDNUpstreamsUnenforceable`.
- **`Cilium`** — a `CiliumNetworkPolicy` with `toFQDNs`, which enforces hostname
  allow-lists via an L7 DNS-proxy rule.
- **`Auto`** (default) — Cilium if its CRD is installed, otherwise Vanilla.

Because the core enforces **one policy per server** (not per upstream
connection), a policy's per-upstream `tools`/`arguments` rules are flattened
together. If you need host-specific tool rules kept apart, use separate policies.

The whole design is **fail-closed by construction**: deny-default + a generated
backstop + a `Degraded` condition mean a policy that cannot compile its backstop
is *visibly unsafe* rather than silently permissive. Deleting the policy clears
the L7 rules from the core.

## Key Config Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `spec.mode` | `Audit` \| `Enforce` | `Audit` | `Audit` observes; `Enforce` blocks (Gatekeeper-style adoption path) |
| `spec.targetRef.kind` | `MCPServer` \| `MCPServerGroup` | — | What the policy attaches to (a group covers every member) |
| `spec.defaultAction` | `Deny` \| `Allow` | `Deny` | Outcome for a tool name no `upstreams[].tools` rule matches |
| `spec.upstreams[].match.host` | string | — | FQDN (needs Cilium) or literal IP/CIDR (any CNI) |
| `spec.upstreams[].tools.allow/deny/requireApproval` | list of globs | — | Precedence: **deny > requireApproval (fail-closed) > allow > defaultAction** |
| `spec.upstreams[].arguments.deny.secretPatterns` | list | — | Named secret-pattern groups to reject |
| `spec.upstreams[].arguments.deny.maxPayloadBytes` | integer | — | Reject argument payloads larger than this |
| `spec.networkBackstop.generate` | bool | `true` | Emit the L3/L4 backstop |
| `spec.networkBackstop.flavor` | `Auto` \| `Cilium` \| `Vanilla` | `Auto` | Backstop implementation |

## What's Next

You now have a deny-by-default egress policy language over both the network and
the tool/argument layers.

- Full spec, status conditions, and backstop flavors --
  [Egress Policy guide](../guides/EGRESS_POLICY.md).
- The enforcement model and the alternatives that were rejected --
  [ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md).
- How this maps to OWASP MCP09 --
  [OWASP MCP Top 10 coverage](../security/OWASP_MCP_TOP_10_COVERAGE.md).
- The public-edge capstone that references this as a compromised-backend control
  -- [23 -- Harden a Public Authenticated Gateway](23-harden-public-gateway.md).
