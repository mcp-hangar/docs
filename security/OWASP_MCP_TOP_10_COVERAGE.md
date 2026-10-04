# OWASP MCP Top 10 — coverage

How MCP Hangar maps against the [OWASP MCP Top 10 (2025)](https://owasp.org/www-project-mcp-top-10/).

Read it beside [what a verdict establishes](VERDICT_LIMITS.md), which says what each
individual record from these mechanisms does and does not prove.

This page is deliberately honest about scope. Hangar is a **policy enforcement plane**: it enforces deterministic policy on the MCP call path and produces an attributable audit trail. It does **not** parse prompt or tool-argument semantics and will not pretend to — so several categories are **out of scope by design**, and a few are **partially** covered with the remaining enforcement tracked in open issues. Each row says which.

| # | Category | Hangar posture | Mechanism / tracking |
| --- | ---------- | ---------------- | ---------------------- |
| MCP01 | Token Mismanagement & Secret Exposure | **Partial** | RFC 8707 audience binding, RFC 9728 protected-resource metadata, JWT/OIDC + JWKS, API keys (SHA-256) with optional expiry; DNS-exfiltration channel closed (operator#56). Open: `mcp-hangar add` writes a prompted secret in plaintext ([mcp-hangar#1653](https://github.com/mcp-hangar/mcp-hangar/issues/1653)) |
| MCP02 | Privilege Escalation via Scope Creep | **Partial** | Per-tenant scoping, tool allow/deny lists, human approval gates on privileged calls. Open: an invalid `tools:` field drops the whole policy ([mcp-hangar#1648](https://github.com/mcp-hangar/mcp-hangar/issues/1648)); a global `developer` can withdraw a tool for all tenants ([mcp-hangar#1656](https://github.com/mcp-hangar/mcp-hangar/issues/1656)) |
| MCP03 | Tool Poisoning | **Partial** | Tool-schema digest pinning, per tenant or for all tenants (detects rug-pull / description drift), enforcement `block` (default), `warn` or `audit`. Open: the pin is compared against the catalogue Hangar last fetched, so unannounced upstream drift is served until a restart or `tools/list_changed` ([mcp-hangar#1693](https://github.com/mcp-hangar/mcp-hangar/issues/1693)) |
| MCP04 | Software Supply Chain & Dependency Tampering | **Partial** | Hangar's own artifacts are cosign-signed + SBOM'd, chart digests pinned (ADR-004); **MCP-server image** digest pinning is checked at admission (operator `v0.13.0`) but the policy **defaults to `warn`** -- `block` is opt-in at startup and a per-server annotation waives it |
| MCP05 | Command Injection & Execution | **Out of scope (by design)** | Hangar does not inspect tool-call arguments for injection. Container-mode command allow-list constrains the server *process*, not call semantics |
| MCP06 | Intent Flow Subversion | **Out of scope (by design)** | Intent/prompt semantics are not parsed. Approval gates offer a human checkpoint, not intent detection |
| MCP07 | Insufficient Authentication & Authorization | **Partial** | RFC 8707 / RFC 9728, JWT/OIDC + JWKS, per-tenant scoping, approval gates, end-to-end identity propagation. Open: auth routes record a caller-supplied actor ([mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)); `oidc.clock_skew_leeway_seconds` is not parsed ([mcp-hangar#1654](https://github.com/mcp-hangar/mcp-hangar/issues/1654)) |
| MCP08 | Lack of Audit and Telemetry | **Covered** | Identity-attributed audit trail per tool call, including calls a gate refuses; SIEM export (CEF, LEEF 2.0, RFC 5424 syslog, JSON-lines); Prometheus metrics; K8s events |
| MCP09 | Shadow MCP Servers | **Partial** | Registry of `MCPServer` resources, admission validation of their spec, per-server egress NetworkPolicy, plus a pod-registration webhook (operator `v0.13.0`) in namespaces labelled `mcp-hangar.io/enforce-egress=true`. It keys on the pod's own `mcp-hangar.io/provider` label, so it catches misconfiguration, not concealment |
| MCP10 | Context Injection & Over-Sharing | **Out of scope (by design)** | Prompt/context content is not inspected. Per-tenant scoping + audit limit blast radius but do not detect context injection |

## Covered

**MCP08 — Audit & Telemetry.** Every tool call -- completed, failed, or refused by a gate -- carries the caller's identity into the audit record, exported to SIEM in CEF, LEEF 2.0, RFC 5424 syslog, and JSON-lines (OTLP is a separate trace/audit-span path, not a SIEM format). Prometheus metrics and Kubernetes events cover the operational side. The SIEM feed is not fail-closed: an unrecognised `MCP_COMPLIANCE_FORMAT` or an unwritable output file disables or drops the export while calls are still served -- see [Compliance Export](../operations/COMPLIANCE.md#delivery-failures).

## Partial (enforcement tracked)

**MCP01 — Token/Secret Exposure.** Audience binding and PRM address token *reuse*; API-key hygiene (SHA-256, optional expiry) and closing the DNS-exfiltration channel (operator#56, fixed) reduce secret leakage. Credential brokering for upstreams (so servers never see raw upstream tokens) is noted as future work in the MCPEgressPolicy epic (operator#53). Open: `mcp-hangar add` writes the secret it prompts for in plaintext to a mode-0644 `config.yaml` ([mcp-hangar#1653](https://github.com/mcp-hangar/mcp-hangar/issues/1653)).

**MCP02 — Scope Creep.** Tool allow/deny lists and per-tenant scoping bound what a caller can reach; approval gates catch privileged calls. There is no automatic detection of gradual scope expansion — that would require behavioral baselining, which the shipped core deliberately does not do. Two open defects weaken the bound: a `tools:` policy with one invalid field is discarded whole, with only a warning ([mcp-hangar#1648](https://github.com/mcp-hangar/mcp-hangar/issues/1648)), and a global `developer` can withdraw or restore a tool for every tenant ([mcp-hangar#1656](https://github.com/mcp-hangar/mcp-hangar/issues/1656)).

**MCP03 — Tool Poisoning.** A poisoned tool changes its schema/description after approval (a "rug pull"). Hangar pins tool schemas -- per tenant, or for every caller under `mcp_servers.<name>.tool_projection.pins` -- and, in the default `block` mode, refuses calls whose schema digest no longer matches the pinned value (`ToolDigestMismatchError`); `warn` and `audit` record the drift instead. This is the direct answer to MCP03, with one open gap: the comparison is made against the catalogue Hangar last fetched, so an upstream that changes its schema without announcing `tools/list_changed` is served until Hangar restarts or re-lists it ([mcp-hangar#1693](https://github.com/mcp-hangar/mcp-hangar/issues/1693)).

**MCP07 — Insufficient Auth.** Authentication and authorization are Hangar's core. Tokens are audience-bound (RFC 8707) so a token minted for one resource cannot be replayed against another; every trusted issuer is advertised through RFC 9728 protected-resource metadata. JWT/OIDC with JWKS validation and per-tenant scoping gate who may call what, and approval gates add a human decision point for high-risk calls. Caller identity is propagated end-to-end. Open: the auth REST routes take the recorded actor (`assigned_by`, `created_by`, ...) from the request body ([mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)), and `oidc.clock_skew_leeway_seconds` is never parsed ([mcp-hangar#1654](https://github.com/mcp-hangar/mcp-hangar/issues/1654)).

**MCP04 — Supply Chain.** Hangar signs and SBOMs its own release artifacts and pins chart digests. Since operator `v0.13.0` an admission check evaluates whether an `MCPServer`'s container image is digest-pinned — but the policy ships as `warn`, which admits the pod and records a warning. Enforcement means setting the operator's image-digest policy to `block` and not waiving it with the per-server annotation. Until an operator is configured that way, mutable tags are accepted in practice.

**MCP09 — Shadow MCP Servers.** OWASP MCP09's prevention control #1 is a registry tied to deployment where unregistered instances fail. Hangar provides the registry (`MCPServer` CRDs), admission validation of their spec, per-server egress policy, and — since operator `v0.13.0` — a pod-registration webhook and default-deny egress in namespaces labelled `mcp-hangar.io/enforce-egress=true`.

The webhook rejects a pod carrying `mcp-hangar.io/provider=<name>` when no `MCPServer` of that name exists in the namespace; a pod without that label is admitted as "not an MCP-server pod". It therefore catches a provider pointed at a server nobody registered — a misconfiguration — rather than a workload that never announces itself, which is what *shadow* means. What constrains that one is the default-deny egress at L3/L4, not admission.

So read MCP09 coverage as "registry, scoped egress, and a gate against mislabelled providers in opted-in namespaces", not "shadow MCP prevented".

## Out of scope by design

**MCP05, MCP06, MCP10** are prompt/intent/context-semantic risks: command injection through tool arguments, intent-flow subversion, and context injection / over-sharing. Detecting these means interpreting the *meaning* of prompts, arguments, and responses. Hangar is a deterministic policy plane — it enforces who-may-call-what and records what happened; it does not guess intent, and adding a probabilistic classifier would contradict its design (binary policy outcomes, no false-positive triage). These categories belong to a different layer (prompt-firewall / semantic-analysis tools) and Hangar does not claim to cover them.

---

*Last reviewed 2026-10-04 against core 2.24.0. Postures marked "Partial" link the open issues that would move them to "Covered".*
