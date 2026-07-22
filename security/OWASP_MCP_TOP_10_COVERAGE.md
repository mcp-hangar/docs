# OWASP MCP Top 10 — coverage

How MCP Hangar maps against the [OWASP MCP Top 10 (2025)](https://owasp.org/www-project-mcp-top-10/).

This page is deliberately honest about scope. Hangar is a **policy enforcement plane**: it enforces deterministic policy on the MCP call path and produces an attributable audit trail. It does **not** parse prompt or tool-argument semantics and will not pretend to — so several categories are **out of scope by design**, and a few are **partially** covered with the remaining enforcement tracked in open issues. Each row says which.

| # | Category | Hangar posture | Mechanism / tracking |
|---|----------|----------------|----------------------|
| MCP01 | Token Mismanagement & Secret Exposure | **Partial** | RFC 8707 audience binding, RFC 9728 protected-resource metadata, JWT/OIDC + JWKS, API keys (SHA-256) with optional expiry; DNS-exfiltration channel closed (operator#56) |
| MCP02 | Privilege Escalation via Scope Creep | **Partial** | Per-tenant scoping, tool allow/deny lists, human approval gates on privileged calls |
| MCP03 | Tool Poisoning | **Covered** | Per-tenant tool-schema digest pinning (detects rug-pull / description drift), policy-configurable block/advisory |
| MCP04 | Software Supply Chain & Dependency Tampering | **Partial** | Hangar's own artifacts are cosign-signed + SBOM'd, chart digests pinned (ADR-004); **MCP-server image** digest pinning tracked in operator#52 |
| MCP05 | Command Injection & Execution | **Out of scope (by design)** | Hangar does not inspect tool-call arguments for injection. Container-mode command allow-list constrains the server *process*, not call semantics |
| MCP06 | Intent Flow Subversion | **Out of scope (by design)** | Intent/prompt semantics are not parsed. Approval gates offer a human checkpoint, not intent detection |
| MCP07 | Insufficient Authentication & Authorization | **Covered** | RFC 8707 / RFC 9728, JWT/OIDC + JWKS, per-tenant scoping, approval gates, end-to-end identity propagation |
| MCP08 | Lack of Audit and Telemetry | **Covered** | Identity-attributed audit trail per tool call; SIEM export (CEF, LEEF 2.0, RFC 5424 syslog, JSON-lines); Prometheus metrics; K8s events |
| MCP09 | Shadow MCP Servers | **Partial** | Registry of `MCPServer` resources, admission validation of their spec, per-server egress NetworkPolicy. Full "unregistered/unpinned → no traffic" enforcement tracked in operator#50 / #51 |
| MCP10 | Context Injection & Over-Sharing | **Out of scope (by design)** | Prompt/context content is not inspected. Per-tenant scoping + audit limit blast radius but do not detect context injection |

## Covered

**MCP03 — Tool Poisoning.** A poisoned tool changes its schema/description after approval (a "rug pull"). Hangar pins tool schemas per tenant and, when policy is set to block, refuses calls whose schema digest no longer matches the pinned value; in advisory mode it records the drift. This is the direct answer to MCP03.

**MCP07 — Insufficient Auth.** Authentication and authorization are Hangar's core. Tokens are audience-bound (RFC 8707) so a token minted for one resource cannot be replayed against another; multi-issuer trust follows RFC 9728. JWT/OIDC with JWKS validation and per-tenant scoping gate who may call what, and approval gates add a human decision point for high-risk calls. Caller identity is propagated end-to-end.

**MCP08 — Audit & Telemetry.** Every allowed tool call carries user identity into the audit record, exported to SIEM in CEF, LEEF 2.0, RFC 5424 syslog, and JSON-lines (OTLP is a separate trace/audit-span path, not a SIEM format). Prometheus metrics and Kubernetes events cover the operational side.

## Partial (enforcement tracked)

**MCP01 — Token/Secret Exposure.** Audience binding and PRM address token *reuse*; API-key hygiene (SHA-256, optional expiry) and closing the DNS-exfiltration channel (operator#56, fixed) reduce secret leakage. Credential brokering for upstreams (so servers never see raw upstream tokens) is noted as future work in the MCPEgressPolicy epic (operator#53).

**MCP02 — Scope Creep.** Tool allow/deny lists and per-tenant scoping bound what a caller can reach; approval gates catch privileged calls. There is no automatic detection of gradual scope expansion — that would require behavioral baselining, which the shipped core deliberately does not do.

**MCP04 — Supply Chain.** Hangar signs and SBOMs its own release artifacts and pins chart digests. It does **not yet** enforce that an `MCPServer`'s container image is digest-pinned (mutable tags are accepted) — tracked in operator#52.

**MCP09 — Shadow MCP Servers.** OWASP MCP09's prevention control #1 is a registry tied to deployment where unregistered instances fail. Hangar provides the registry (`MCPServer` CRDs), admission validation of their spec, and per-server egress policy — but does **not yet** guarantee that an unregistered or unpinned server gets no traffic (no admission-time registration enforcement, no default-deny egress). That enforcement is tracked in operator#50 (admission) and operator#51 (default-deny egress). Until it lands, treat MCP09 coverage as "registry + scoped egress", not "shadow MCP prevented".

## Out of scope by design

**MCP05, MCP06, MCP10** are prompt/intent/context-semantic risks: command injection through tool arguments, intent-flow subversion, and context injection / over-sharing. Detecting these means interpreting the *meaning* of prompts, arguments, and responses. Hangar is a deterministic policy plane — it enforces who-may-call-what and records what happened; it does not guess intent, and adding a probabilistic classifier would contradict its design (binary policy outcomes, no false-positive triage). These categories belong to a different layer (prompt-firewall / semantic-analysis tools) and Hangar does not claim to cover them.

---

*Last reviewed 2026-07-18 against the shipped code. Postures marked "Partial" link the open issues that would move them to "Covered".*
