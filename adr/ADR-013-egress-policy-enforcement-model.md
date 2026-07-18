# ADR-013: Egress Policy Enforcement Model (MCPEgressPolicy)

**Status:** Accepted
**Date:** 2026-07-18
**Authors:** MCP Hangar Team
**Related:** Builds on the enforcement roadmap (mcp-hangar-operator #50 admission, #51 default-deny egress, #52 image pinning — shipped as operator phases 1–3, v0.13.0). Decision issue: mcp-hangar-operator#53. Positioning: mcp-hangar-website#85 (enforcement-plane reposition). Depends on the interceptor/pin posture in [ADR-012](ADR-012-interceptor-sep-pin-tracking-policy.md).

## Context

Phases 1–3 of the enforcement roadmap close the **binary registration gap**: a namespace opted into enforcement (`mcp-hangar.io/enforce-egress=true`) gets a default-deny egress, unregistered provider pods fail admission, and a registered server's egress is withheld until its image is digest-pinned. That gives a governed **on/off switch** — "may this server receive traffic at all?"

It does not answer the question the product thesis is actually about: *which tool calls, with which arguments, to which upstreams — and what happens when the answer is no.* Naming Hangar a "policy enforcement plane" (mcp-hangar-website#85) is only honest once a **declarative policy language** exists above the binary switch. This ADR fixes the enforcement *model* for that language before any API is committed, because the resulting CRD is public and long-lived.

Standards/market anchors (verified 2026-07-18):

- OWASP MCP09:2025 — prevention control #1 (registry tied to deployment) is #50/#51 territory; controls #3–#5 (baseline templates, IAM binding, anomalous-endpoint alerting) map to this layer.
- Errico/Ngiam/Sojan (arXiv:2511.20920, cited in the NSA/DoD CSI on MCP security, 6/2026): "inline policy enforcement" + "centralized governance using private registries or gateway layers."
- MCP spec Security Best Practices (2026-07-28 release): token passthrough forbidden — the credential-brokering consequence lands in this layer, not below it.

The enforcement mechanism is the load-bearing decision. The realistic options are: (a) transparent TLS interception of arbitrary egress; (b) in-kernel L7 protocol parsing (eBPF/Tetragon); (c) explicit-proxy enforcement on the connections Hangar already originates, with a network backstop that prevents bypass. Each has a very different trust, complexity, and failure profile.

## Decision

**Explicit-proxy enforcement + a policy-generated network backstop. No transparent TLS interception and no eBPF protocol parsing in v1.**

1. **L7 (MCP semantics: tools, arguments, responses) is enforced in the data plane Hangar already operates.** Clients connect to Hangar; Hangar originates the upstream TLS connection. A policy therefore governs connections Hangar *already makes* — no new interception surface, no private keys for traffic Hangar does not terminate. `MCPEgressPolicy` formalizes policy on exactly those connections.

2. **An L3/L4 network backstop guarantees the data plane cannot be bypassed.** Policy compilation *generates* the backstop rather than leaving it as operator homework: the (phase-1) `pkg/networkpolicy/builder.go` path is extended so a compiled policy emits default-deny egress + allow-to-Hangar + allow-DNS in governed namespaces (Vanilla flavor), or a `CiliumNetworkPolicy` with `toFQDNs` from the policy's declared upstreams (Cilium flavor), with CNI auto-detection.

3. **The trust model is documented verbatim, in the API and the docs:** *a policy without the network backstop is a suggestion; if a pod can bypass DNS + NetworkPolicy, it can bypass Hangar.* The backstop is not optional decoration — it is what makes the L7 policy an enforcement rather than a recommendation.

4. **New CRD `MCPEgressPolicy` (existing group, v1alpha1)**, shape fixed by this ADR:
   - `spec.mode: Audit | Enforce` — **Audit is the default**, giving a Gatekeeper-style adoption path (observe violations before they block).
   - `spec.targetRef` attaches policy to an `MCPServer`/`MCPServerGroup`, never to raw pods.
   - `spec.defaultAction: Deny` — deny-by-default; `upstreams[]` is the allow-list.
   - `spec.upstreams[].match` references existing trust primitives rather than duplicating them: `toolSchemaDigestRef` (the per-tenant tool-schema pinning core already has), `imageDigest` (defers to #52 semantics), `issuers` (multi-issuer trust).
   - `spec.upstreams[].tools`: glob allow / deny / `requireApproval` — the last routes into the human-in-the-loop approval gates core already has.
   - `spec.upstreams[].arguments`: **deterministic** secret-pattern and size limits only. Full DLP and any ML-based detection are explicit anti-goals.
   - `spec.networkBackstop: { generate, flavor: Auto|Cilium|Vanilla }`.
   - `status.conditions`: `Compiled`, `BackstopApplied`, `Degraded(FailOpenRisk)`.
   - CEL validation; a conversion strategy is required from day one because this API is public.

5. **Compilation reuses existing distribution.** The operator reconciles `MCPEgressPolicy` into a data-plane policy document delivered over the **same channel that already feeds routing config** to the data plane — no new distribution protocol — and the same reconcile emits the network backstop.

## Consequences

- Hangar gains a **policy language**, not just a switch — the substance behind the enforcement-plane category claim, without taking on the trust and operational burden of terminating traffic Hangar does not already terminate.
- **No new key-management or MITM surface.** Enforcement is scoped to connections Hangar originates; anything a workload does outside Hangar is the backstop's job (deny), not the L7 layer's.
- **Fail-closed by construction.** Deny-default + generated backstop + a `Degraded(FailOpenRisk)` condition mean a policy that cannot compile its backstop is visibly unsafe rather than silently permissive.
- **Cost (accepted):** enforcement covers MCP-over-Hangar traffic plus the network backstop, *not* arbitrary application-layer egress. A workload that bypasses DNS + NetworkPolicy bypasses Hangar — stated as the trust boundary, not hidden.
- **Cost (accepted):** `Audit` default means early adopters get visibility before enforcement; a policy left in `Audit` enforces nothing. This is deliberate (adoption path), and surfaced in status.
- Known gotcha to test before shipping the Cilium flavor: `toFQDNs` × NodeLocal DNSCache interplay.
- v1 deliberately forecloses eBPF L7 parsing and transparent TLS interception; revisiting either is a future ADR, not an implementation detail.

## Alternatives considered

- **Transparent TLS interception (mitmproxy-style) of all egress.** Rejected for v1: requires Hangar to hold keys / a trusted CA for traffic it does not originate, is brittle against pinned/mTLS upstreams, and enlarges the attack surface it is meant to shrink. The explicit-proxy model gets the same L7 visibility for the traffic that matters (MCP-over-Hangar) without it.
- **eBPF / Tetragon in-kernel L7 protocol parsing.** Rejected for v1: high operational and portability cost (kernel/CNI coupling), and MCP-semantic parsing in-kernel is speculative. Retained as a possible future backstop-observability layer, not the enforcement primitive.
- **Service-mesh sidecar (Envoy/Istio) as the enforcement point.** Rejected for v1: pushes a heavy mesh dependency onto every adopter and still would not understand MCP tool/argument semantics without custom filters. The data plane Hangar already runs is a better-fit enforcement point.
- **Backstop as operator documentation ("apply your own NetworkPolicy").** Rejected: that is exactly the fail-open homework phase 1 removed; if the backstop is not generated by policy compilation, "enforcement" is advisory.

## References

- Decision issue / epic: mcp-hangar-operator#53.
- Enforcement roadmap phases: operator #68 (phase 1), #69 (phase 2), #70 (phase 3), released v0.13.0; chart parity helm-charts#62/#63.
- Positioning: mcp-hangar-website#85; OWASP MCP Top 10 coverage (docs security page, #65).
- Builder to extend: `pkg/networkpolicy/builder.go` (operator).
- Reused primitives (core): tool-schema digest pinning, approval gates, SIEM export (LEEF 2.0 / RFC 5424 / OTLP).
