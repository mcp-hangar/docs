# Compliance Posture — EU AI Act and SOC 2

**Status:** Living document. Maintainer-authored, reviewed against Regulation (EU) 2024/1689 (the "AI Act") and the AICPA 2017 Trust Services Criteria (2022 revision points of focus).

**What this document is:** an honest mapping of what MCP Hangar's features actually provide toward compliance work that *you* — the organization deploying it — have to do.

**What this document is not:** legal advice, a certification, an attestation, or a claim that running MCP Hangar makes you "compliant" with anything. No software does that. Anyone telling you otherwise is selling something.

---

## 1. Role model: who is responsible for what

MCP Hangar is open-source, self-hosted infrastructure. The project distributes code under the MIT license. There is no hosted service and no SaaS offering; the project exists exclusively as software you download and operate yourself. Everything below describes that distribution model — if it ever changed, this document would be invalid and would need to be rewritten before anything else shipped. Consequently, as of today:

- The project **has no access to your deployment and does not process your data**. The software contains no telemetry, no usage reporting, and no backchannel to the maintainers. All network egress goes to endpoints **you** configure: your OIDC issuers (metadata and JWKS fetches), your container registries (digest resolution), your SIEM (event export). This is a verifiable property of the codebase, not a policy statement — audit it.
- The project is **not a vendor** in your compliance chain. There is no DPA to sign, no sub-processor to list, no vendor questionnaire we can answer — because there is no service relationship.
- **You operate the software.** Every regulatory obligation discussed below sits with the organization that deploys MCP Hangar, exactly as it would for nginx, PostgreSQL, or Envoy.

This is not a disclaimer of convenience; it is the architecture. MCP Hangar runs entirely inside your perimeter.

## 2. Is MCP Hangar itself an "AI system" under the AI Act?

**No.** Under Art. 3(1), an AI system is a machine-based system that "infers, from the input it receives, how to generate outputs" with some degree of autonomy. MCP Hangar does not infer anything:

- Policy enforcement is **deterministic**: rules in, decisions out. Same input, same output, every time.
- There is no ML model in the codebase (verifiable by inspection — this claim is re-checked at each release). The only component with "classifier" in its name (`ErrorClassifier`) is heuristic retry logic that labels technical errors as transient or permanent. It has no effect on any person and involves no learned behavior.
- Behavioral profiling of MCP servers is threshold- and rule-based anomaly detection over recorded events — statistics, not inference in the Art. 3(1) sense.

Therefore MCP Hangar carries **no direct obligations as an AI system provider**. Its relevance to the AI Act is entirely instrumental: it is infrastructure that AI system providers and deployers can use to satisfy *their* obligations.

If a future release introduces an ML-based component, this section gets revisited as part of that release — the Art. 3(1) analysis is a release-gate check, not a one-time assertion.

## 3. EU AI Act: feature → obligation mapping

The AI Act's high-risk requirements (Chapter III, applicable to Annex III systems from 2 August 2026) fall on the **provider** of the AI system (Arts. 8–15) and on the **deployer** (Art. 26). If you route your AI agents' tool access (MCP traffic) through MCP Hangar, the following mappings hold.

### 3.1 For providers of high-risk AI systems

| AI Act obligation | Article | What MCP Hangar provides |
|---|---|---|
| Automatic recording of events (logs) over the system's lifetime; logging capability must be designed in | Art. 12(1)–(2) | Event-sourced, append-only audit trail of every MCP tool invocation, identity, decision, and policy outcome ([ADR-002](../adr/ADR-002-event-sourcing.md)). Configurable retention. |
| Logs sufficient to identify situations presenting risk | Art. 12(2)(a), Art. 79 | Detection events, anomaly flags, and policy-violation records are first-class event types, not free-text log lines. |
| Human oversight measures, including the ability to intervene or interrupt (the "stop button") | Art. 14(3)–(4), esp. 14(4)(e) | Approval gates requiring a mandatory human decision before designated tool calls proceed; manual override; suspension controls. The gate contains no AI recommendation component — the decision is fully human, which avoids the automation-bias problem Art. 14(4)(b) warns about. |
| Accuracy, robustness and cybersecurity of the system | Art. 15 | Supportive, not sufficient: per-tenant digest pinning, audience binding (RFC 8707), multi-issuer trust, and identity propagation reduce the supply-chain and confused-deputy attack surface of the tool-calling path. Art. 15 covers far more than tool access; Hangar addresses one layer. |

### 3.2 For deployers of high-risk AI systems

| AI Act obligation | Article | What MCP Hangar provides |
|---|---|---|
| Assign human oversight to competent, trained persons | Art. 26(2) | Approval gates give those persons an actual mechanism, with RBAC controlling who can approve what. The *assignment and training* is your job. |
| Monitor operation of the system; suspend use and inform the provider on risk | Art. 26(5) | Governance dashboards, SIEM export, and suspension controls provide the monitoring and the kill switch. The *process* around them is your job. |
| Retain automatically generated logs for at least six months | Art. 26(6) | Retention is configurable; set it ≥ 6 months (or longer where other EU/national law requires) and the audit trail satisfies the record-keeping substrate. |

### 3.3 What MCP Hangar explicitly does not do under the AI Act

- It does not perform, contribute to, or substitute for a **conformity assessment** (Art. 43).
- It does not produce **technical documentation** per Annex IV — it produces *evidence you can cite inside* that documentation.
- It does not make any system "AI Act ready." Readiness is a property of your system, your processes, and your paperwork — not of a gateway in front of your tools.
- It does not address obligations unrelated to the tool-access path: data governance (Art. 10), transparency to affected persons (Arts. 13, 50), risk management systems (Art. 9), registration (Art. 49).

## 4. SOC 2: feature → Trust Services Criteria mapping

SOC 2 is an attestation of **your organization's** controls, performed by a licensed CPA firm, over **your** system. A codebase you download and run yourself is outside SOC 2's object of attestation by definition — the attestable thing is your deployment. MCP Hangar's role in that audit is as a control implementation and an evidence source inside your scope.

| TSC | Criteria area | MCP Hangar as control / evidence |
|---|---|---|
| CC6.1–CC6.3 | Logical access controls | RBAC over tool access and approvals; OAuth resource-server enforcement with audience binding (RFC 8707); multi-issuer trust with explicit issuer allow-lists; end-to-end identity propagation making tool calls attributable to a principal (when configured — anonymous access paths, if you allow them, are your scoping decision). |
| CC7.2–CC7.3 | System monitoring, anomaly detection and evaluation | Behavioral profiling of MCP server activity; detection events; export to your SIEM in CEF/LEEF 2.0, RFC 5424 syslog, JSONL, and OTLP — meaning the evidence lands where your auditor already looks ([COMPLIANCE.md](./COMPLIANCE.md) covers the formats). |
| CC7.4 | Incident response support | Suspension controls and human-in-the-loop gates give responders an enforcement point; the event log gives them a timeline. Append-only is enforced at the application layer; the deployer controls the underlying storage, so pair it with database-level immutability or WORM/object-lock storage where your audit requires tamper *evidence*, not just tamper *resistance*. |
| CC8.1 | Change management | Per-tenant digest pinning (only reviewed, pinned server images run), canary and version routing (controlled rollout of tool-server changes), with every change recorded in the audit trail. |

Evidence generation in practice: an auditor asking "show me who could invoke tool X in Q3 and who approved the exceptions" can be answered from the event store and SIEM exports; "prove the log wasn't altered" is answered by the event store *plus* the storage-immutability controls you put under it. That — and only that — is what "exportable audit evidence for compliance workflows" on the website refers to.

## 5. Non-claims (read this twice)

1. MCP Hangar is **not certified** under SOC 2, ISO 27001, ISO 42001, or anything else. Certification attaches to an organization operating a system; there is no operated service here to audit. The thing that *can* be in audit scope is your deployment of it.
2. Deploying MCP Hangar does **not** make you compliant with the AI Act, SOC 2, GDPR, or any framework. It gives you controls and evidence; compliance is a property of your whole organization.
3. Nothing here is **legal advice**. Map your own system against the AI Act with counsel; this document exists so that mapping is grounded in what the software actually does rather than what a landing page once implied.
4. Historical note: earlier marketing copy claimed "SOC2 evidence generation. EU AI Act readiness." The first half was imprecise, the second half was unsubstantiated; both were replaced ([website#70](https://github.com/mcp-hangar/mcp-hangar-website/pull/70)). This document is the substantiation that should have existed first.

## 6. References

- Regulation (EU) 2024/1689 — Arts. 3(1), 12, 14, 15, 26, 43; high-risk obligations for Annex III systems apply from 2 August 2026.
- AICPA Trust Services Criteria (2017, 2022 revised points of focus) — CC6, CC7, CC8.
- [ADR-002 — Event Sourcing](../adr/ADR-002-event-sourcing.md) (audit-trail architecture).
- [ADR-010](../adr/ADR-010-retire-agent-cloud-tier.md) (supersedes ADR-006; current enforcement architecture).
- [operations/COMPLIANCE.md](./COMPLIANCE.md) (SIEM export formats).
