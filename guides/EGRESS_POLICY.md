# Egress Policy (MCPEgressPolicy)

> **New to this?** [The L7 MCPEgressPolicy language](https://mcp-hangar.io/learn/the-l7-mcpegresspolicy-language) is the concept behind this page.

Declarative, deny-by-default egress policy for MCP servers: control which upstreams a server may reach, which tool calls it may make, and what happens when the answer is no.

## Overview

`MCPEgressPolicy` is the policy layer above the binary registration switch. Registration (an `MCPServer` exists), default-deny egress, admission rejection of unregistered pods, and image-pin coupling answer *"may this server receive traffic at all?"* An egress policy answers the next question: *"which upstreams, which tool calls, with which arguments — and what happens on a violation?"*

Enforcement has two layers, applied together:

| Layer | Enforced by | Governs |
| ------- | ------------- | --------- |
| **L3/L4** (network backstop) | operator → `NetworkPolicy` or `CiliumNetworkPolicy` | which upstream hosts/CIDRs the server's pods can reach |
| **L7** (semantics) | core, on connections Hangar proxies | which tool calls (by name) and which arguments are allowed |

The trust boundary is explicit: **a policy without the network backstop is a suggestion.** If a pod can bypass DNS and NetworkPolicy, it can bypass Hangar. The backstop is what makes the L7 policy enforcement rather than a recommendation. See [ADR-013](../adr/ADR-013-egress-policy-enforcement-model.md) for the model and the alternatives that were rejected (no transparent TLS interception, no eBPF protocol parsing in v1).

## Prerequisites

- The operator, with the `MCPEgressPolicy` CRD installed. The `MCPEgressPolicy` reconciler shipped in operator **v0.14.0**; v0.13.0 shipped the rest of the enforcement roadmap.
- The target namespace should be opted into egress enforcement with the label `mcp-hangar.io/enforce-egress=true`, so the namespace default-deny is in place and the backstop has something to build on. See [Governed Namespaces](KUBERNETES.md#governed-namespaces) for how the operator keeps that default-deny in place.
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
BackstopEnforceable=True (EnforcerObserved)
L7Delivered=True (Delivered)
Degraded=False (NotDegraded)
```

`kubectl get` shows the backstop's enforcement and the L7 delivery as columns:

```
$ kubectl -n prod get mcpegresspolicies
NAME      MODE      BACKSTOP   L7     TARGET   DEFAULT   AGE
gh-only   Enforce   Enforcing  True   srv      Deny      2m
```

A pod behind this policy reaches `api.github.com` (HTTP 200) but not any other host (connection times out), while DNS still resolves.

### Governing a group

`targetRef.kind: MCPServerGroup` applies one policy to every member of a group. The operator resolves the group's member servers and scopes the backstop to all of them (`mcp-hangar.io/provider In [members]`).

Since operator 0.17.5 the policy follows membership as it changes: a server that starts matching the group's selector is added to the backstop and gets the L7 policy pushed within seconds, one that stops matching is dropped, and a server deleted and recreated under the same name gets its L7 policy back. A group selector edited to match nothing removes the backstop and reports `TargetNotFound`. Earlier releases resolved members once per reconcile, so a later member ran without the policy until the next resync.

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
| ------- | ------ | --------- | ------------- |
| `mode` | `Audit` \| `Enforce` | `Audit` | `Audit` observes violations; `Enforce` blocks. Audit-default gives a Gatekeeper-style adoption path. |
| `targetRef.kind` | `MCPServer` \| `MCPServerGroup` | — | What the policy attaches to. A group applies the policy to every member server. |
| `targetRef.name` | string | — | Referent name, resolved in the policy's namespace. |
| `defaultAction` | `Deny` \| `Allow` | `Deny` | Outcome for a tool name that no `upstreams[].tools` rule matches. |
| `upstreams[]` | list | — | The allow-list. With `defaultAction: Deny`, an empty list denies everything except the DNS/backstop paths. |
| `networkBackstop` | object | generate/Auto | Controls the generated L3/L4 backstop (below). |

### `upstreams[]`

| Field | Type | Description |
| ------- | ------ | ------------- |
| `name` | string | Rule name, unique within the policy (enforced by a CEL rule). |
| `match.host` | string | Upstream host: an FQDN (needs Cilium), or a literal IP/CIDR (works under any CNI). |
| `match.toolSchemaDigestRef` | string | References an existing per-tenant tool-schema pin. |
| `match.imageDigest` | `required` \| `inherited` | How the target's image pin gates this upstream. |
| `match.issuers` | list | Restricts which token issuers may be brokered to this upstream. |
| `tools.allow` / `tools.deny` / `tools.requireApproval` | list of globs | Tool-name globs. Precedence: **deny > requireApproval > allow > defaultAction**. |
| `headers.allow` / `headers.deny` / `headers.requireApproval` | list | `Mcp-Param-*` header selectors; see [the policy language recipe](../cookbook/24-egress-policy-language.md). |
| `arguments.deny.secretPatterns` | list | Named secret-pattern groups to reject (below). |
| `arguments.deny.maxPayloadBytes` | integer | Reject tool-call argument payloads larger than this. |

### `networkBackstop`

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `generate` | bool | `true` | Emit the L3/L4 backstop. `false` removes it (the policy then relies on the namespace default-deny alone); the L7 rules are still delivered to core and reported on `L7Delivered`. |
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
2. `requireApproval` — the call is routed into the interactive approval gate
   (core 2.11.0): a typed pending approval is created and delivered on the
   configured channel, resolution requires `approval:resolve`, and the
   decision is revalidated at dispatch — so an approval granted while a
   policy was in force is not usable after that policy changes, and `deny`
   still wins if the policy hardens during the hold. With no `approvals:`
   block the call is held on the default `event_stream` channel. Only with
   the gate turned off (`approvals: {enabled: false}`) does the **verdict
   fail closed** -- refused as `EgressPolicyApprovalRequiredError`, exactly
   as before 2.11.0 (see [Limitations](#limitations-and-notes)).
3. `allow` — permit.
4. otherwise — the policy's `defaultAction`.

Globs are case-sensitive for determinism (`get_*` does not match `GET_user`).

**Argument scanning** rejects a tool call whose arguments contain a configured secret pattern or exceed `maxPayloadBytes`. A secret or oversized payload **denies the call even when the tool itself is allowed** — deny always wins. Arguments that cannot be serialized for inspection also fail closed.

**How the L7 policy is delivered.** The operator compiles the policy's per-upstream `tools`/`arguments` rules into a single per-server policy — the union of the upstreams' allow/deny/require-approval globs and secret-pattern groups, and the most restrictive (smallest) `maxPayloadBytes` — and pushes it to the core (requires `--hangar-url`). The core enforces it at the tool-invocation chokepoint: a denied call raises before it reaches the upstream; an approval-gated call is blocked pending approval. Deleting the policy clears it from the core. Whether every target server accepted the push is reported on the `L7Delivered` condition (see [Status conditions](#status-conditions)).

The L7 half does not depend on the backstop. Since operator 0.17.5 a policy with `networkBackstop.generate: false` still has its rules pushed; earlier releases stopped at the backstop decision and delivered nothing. A `generate: false` policy in `Enforce` mode written on the assumption that only its backstop mattered will start blocking, or routing to approval, the tool calls its rules name. A `generate: false` policy whose target does not exist reports `Compiled=False` / `TargetNotFound` and `Degraded=True`.

### Secret-pattern groups

`secretPatterns` names groups; each maps to deterministic value-regexes shared with Hangar's output redactor, so what the redactor masks on the way out is what a policy refuses on the way in (`pem-blocks` is the exception: the redactor carries no PEM pattern):

| Group | Detects |
| ------- | --------- |
| `aws-keys` | AWS access key IDs (`AKIA…`) |
| `jwt` | JSON Web Tokens (`eyJ….…`) |
| `pem-blocks` | PEM private-key blocks |
| `github-tokens` | GitHub PATs / OAuth / server / refresh tokens |
| `stripe-keys` | Stripe live/test/restricted keys |
| `slack-tokens` | Slack tokens (`xox…`) |
| `google-api-keys` | Google API keys (`AIza…`) |
| `bearer-tokens` | `Bearer …` credentials |
| `npm-tokens`, `pypi-tokens` | npm / PyPI tokens |

An unknown group name refuses the whole policy: the core answers the push with
`400` `invalid_l7_policy`, naming the unknown group and listing the known ones.
CRD validation does not catch it -- the field is a plain string list -- so a
misspelt `github-token` passes `kubectl apply` and is refused at delivery.

## Surviving a gateway restart

The operator delivers the L7 policy when it reconciles the `MCPEgressPolicy`.
Since operator 0.17.4 it also delivers every policy again when a gateway pod
becomes Ready -- a new pod, a container restarted in place, or every Ready
gateway pod when the operator itself starts. It finds gateway pods with
`--hangar-gateway-selector` (default `app.kubernetes.io/name=mcp-hangar`, the
mcp-hangar chart's label; empty disables it). A selector that matches no pod
makes this a no-op, and the operator logs an error-level line saying so. With
more than one gateway replica and no shared backend, the push goes through the
`--hangar-url` Service and reaches whichever replica it routes to, not
necessarily the one that restarted.

Where the re-delivery does not reach -- an older operator, a selector that
matches nothing, a replica the Service did not route to -- whatever the gateway
does not keep across a restart is **not enforced from the restart until the
next reconcile**, which can be hours. The L3/L4 backstop is not affected; it
lives in the cluster, not in the gateway.

Whether the gateway keeps the policy depends only on how it stores its fleet
(core 2.22.1 and later):

| Deployment | After a gateway restart | `persisted` in the push response |
| ---------- | ----------------------- | -------------------------------- |
| No persistence backend -- the chart default, `persistence.backend: ""` | lost until the operator delivers it again | `false`; the gateway logs `l7_policy_not_persisted` at warning |
| `sqlite` on the chart's default `emptyDir` | kept across a container restart, lost when the pod is replaced -- that is, on every rollout | `true` -- the gateway cannot see what its volume is |
| `sqlite` with `persistence.sqlite.persistentVolume.enabled: true` | kept | `true` |
| `postgresql` | kept; each replica reads it back when it starts | `true` |
| `MCP_PERSISTENCE_ENABLED=true` with `MCP_AUTO_RECOVER=false` | lost: written, never read back | `false`, reason `auto_recover_off` |

This holds for servers declared in `config.yaml` and servers registered over the
REST API alike. Clearing a policy is kept the same way, so a restart does not
bring back a policy the operator deleted. Core releases before 2.22.1 lost the
policy of every server `config.yaml` declares on every restart, whatever the
backend ([mcp-hangar#1306](https://github.com/mcp-hangar/mcp-hangar/issues/1306)).

Two failures at start are not covered by the table:

- **A stored policy that no longer parses fails closed.** The server denies
  every tool until the operator delivers its policy again, and the gateway logs
  `l7_policy_unreadable_denying_all` at error.
- **A database that cannot be read at start fails open.** The gateway starts
  anyway, so that the servers `config.yaml` declares keep serving, logs the
  failure at error, and serves them without their stored policies until the
  operator delivers them again.

`persisted` answers for the gateway's configuration, not for its storage: a
SQLite file on an `emptyDir` reports `true` and is still gone after a rollout.
To keep the policy, choose a durable backend in the chart values -- PostgreSQL,
which multiple replicas need anyway, or SQLite on a persistent volume:

```yaml
persistence:
  backend: sqlite
  sqlite:
    persistentVolume:
      enabled: true
```

To find a deployment that does not keep it, search the gateway log for
`l7_policy_not_persisted`. It is logged on every push, so a deployment that
drops the policy on restart shows it on every reconcile.

## Status conditions

| Condition | Meaning |
| ----------- | --------- |
| `Compiled` | The policy was structurally compiled. |
| `BackstopApplied` | The L3/L4 backstop is in place (`False` with `BackstopGenerationDisabled` when `generate: false`). |
| `BackstopEnforceable` | Whether anything in the cluster enforces the written backstop: `True` / `EnforcerObserved` when the operator finds a policy-enforcing API or a known CNI agent, `False` / `NoEnforcerObserved` when it finds neither (`status.backstopEnforcement: Unenforced`; the `Backstop` column of `kubectl get`). |
| `L7Delivered` | Whether core took the compiled L7 policy (operator 0.17.5). `True` / `Delivered` once every target server accepted the push; `True` / `DeliveredNotPersisted` when core took it but has no persistence backend (see [Surviving a gateway restart](#surviving-a-gateway-restart)); `False` / `CoreAuthRejected`, `CoreUnreachable` or `PushFailed`, naming the server whose push failed; `Unknown` / `CoreIntegrationOff` when the operator runs without `--hangar-url`. Shown as the `L7` column of `kubectl get mcpegresspolicies`. |
| `Degraded` | An at-risk state: `FQDNUpstreamsUnenforceable` (FQDN upstreams under the Vanilla flavor), `CiliumUnavailable` (Cilium requested, CRD absent), `TargetNotFound`, `EnforcementNotObserved` (nothing observed to enforce the backstop), or `L7PushFailed` (`L7Delivered=False`). |

`Compiled` and `BackstopApplied` say nothing about core. Before operator 0.17.5 a policy whose L7 push core refused -- an API key without `policy:write`, a core that was down, a payload core rejected -- read `Compiled=True` and `Degraded=False`, with a Warning Event as the only trace. It now reads `L7Delivered=False` and `Degraded=True` / `L7PushFailed`, so an alert on `Degraded` may fire on a policy that has been undelivered since it was created. Fix the key's permissions or core's reachability; the next reconcile clears it.

## Limitations and notes

- **L7 needs core integration.** The tool-call / argument rules are enforced only when the operator runs with `--hangar-url`; otherwise a policy applies its L3/L4 backstop, its L7 rules are not delivered, and it reports `L7Delivered=Unknown` / `CoreIntegrationOff`.
- **The CR does not report whether the gateway still holds the L7 policy.** `L7Delivered=True` means core accepted the last push, not that the gateway kept it. A gateway without durable storage drops it on restart until it is delivered again; see [Surviving a gateway restart](#surviving-a-gateway-restart). To see what a gateway holds right now, `GET /api/mcp_servers/{id}/l7_policy`.
- **FQDN enforcement requires Cilium.** Under other CNIs, list upstreams as CIDRs, or accept that hostname upstreams are denied (fail closed) and surfaced via `Degraded`.
- **L7 rules are merged per server.** Because the core enforces one policy per server (not per upstream connection), a policy's upstream `tools`/`arguments` rules are flattened together (see [above](#l7-semantics)). Scope host-specific tool rules with separate policies if you need them kept apart.
- **`requireApproval` needs the approval gate to be interactive** — since core 2.11.0 a gated call blocks on the approval gate (typed pending approval, `approval:resolve` chokepoint, dispatch-time revalidation), delivered on the default `event_stream` channel when nothing else is configured; on a deployment with the gate turned off (`approvals: {enabled: false}`) it fails closed, as it always did. `Audit` mode records the would-be verdict and never asks a human.
- **`Enforce` governs new connections only — it does not cut established ones.** This is normal NetworkPolicy behaviour: the CNI keeps established conntrack entries, so a server holding a TCP session opened *before* the policy landed keeps talking through it until that connection closes. Measured live (kind + Calico): data sent after a restrictive policy applied still flowed through the pre-existing session. Flipping `Audit` → `Enforce` and seeing `BackstopApplied: True` therefore means *"no new disallowed connections"*, not *"all disallowed traffic stopped now"*. To guarantee existing sessions are cut, roll the server's pods after switching to `Enforce` (`kubectl rollout restart`).
- **stdio servers are out of scope of the L3/L4 backstop.** An in-pod stdio MCP server generates no network traffic of its own, so an `MCPEgressPolicy` backstop has nothing to act on — your transport choice decides whether the network half of this feature applies to you at all. The L7 half (tool/argument rules) still applies, because it is enforced in the data plane Hangar operates, not on the wire.
- **`toFQDNs` upstreams do not survive NodeLocal DNSCache.** This bullet used to say the operator's DNS-topology configuration (`ExtraDNSEgressPeers`, set with `--dns-egress-cidrs`) covered the same ground. It does not. Measured live (kind + Cilium 1.20.1 + the upstream node-local-dns addon, kubelet pointed at `169.254.20.10`): a governed pod resolves through the cache whether or not the DNS egress rule names it -- the destination is the node itself, so that rule is not the control point -- and the allow-listed hostname is **denied anyway**, because Cilium's DNS proxy never observes a lookup the cache answers and the `toFQDNs` allow-list stays empty. Enforcement survives (a name outside the allow-list stays blocked), so this fails closed: on such a cluster every hostname upstream is unreachable while the policy reports `BackstopApplied: True`. `ExtraDNSEgressPeers` is also not read on the Cilium path at all -- that builder's DNS rule is a fixed `toEndpoints` selector on kube-dns. Use CIDR upstreams there, or keep the cluster's pods resolving through kube-dns, until [mcp-hangar-operator#178](https://github.com/mcp-hangar/mcp-hangar-operator/issues/178) is fixed.

## See also

- [ADR-013: Egress Policy Enforcement Model](../adr/ADR-013-egress-policy-enforcement-model.md) — the enforcement model and rejected alternatives.
- [MCP Server Groups](MCP_SERVER_GROUPS.md) — the aggregation the group target will attach to.
- [OWASP MCP Top 10 coverage](../security/OWASP_MCP_TOP_10_COVERAGE.md) — how this maps to MCP09 and related controls.
- [What a verdict establishes](../security/VERDICT_LIMITS.md) — what an L7 `deny`, an Audit-mode observation and an `Mcp-Param-*` selector match do and do not prove to someone reading the record later.
