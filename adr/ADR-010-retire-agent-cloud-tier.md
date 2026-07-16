# ADR-010: Retire the Agent + Hangar Cloud Product Tier

**Status:** Accepted
**Date:** 2026-07-16
**Authors:** MCP Hangar Team
**Supersedes:** ADR-005 (fully), ADR-006 (fully); ADR-004, ADR-009 (in part)

## Context

The `hangar-agent` Go sidecar and the Hangar Cloud SaaS backend it connected to
have been retired:

- **`hangar-cloud`** (the SaaS control plane) — repository archived and private;
  the REST API no longer exists.
- **`mcp-hangar-agent`** (the Go interceptor sidecar) — repository archived.
- The **`hangar-agent` Helm chart** — removed from `helm-charts`
  ([helm-charts#43](https://github.com/mcp-hangar/helm-charts/pull/43)).
- **`terraform-provider`** — a pure Hangar Cloud REST client with no other
  backend (11 resources + 3 data sources, all against `cloud.mcp-hangar.io`) —
  deprecated and archived
  ([terraform-provider#13](https://github.com/mcp-hangar/terraform-provider/pull/13)).
- **Core (`mcp-hangar`)** — the `src/mcp_hangar/cloud/` connector, the
  `POST /agent/policy` endpoint, the `--cloud-key`/`--cloud-url` flags, and the
  `agent` RBAC role are removed
  ([mcp-hangar#490](https://github.com/mcp-hangar/mcp-hangar/pull/490)).

Four accepted ADRs assumed a live agent/cloud tier and are now partly or wholly
invalidated.

## Decision

Retire the agent + Hangar Cloud tier as a product surface. The supported
deployment surface is the **open-source control plane (`mcp-hangar`) + the
Kubernetes operator + the Helm charts**. Governance stays where it already runs
live — **in-process in core** (per-tenant tool projection, digest pinning, and
policy resolution on the call path) — not in an external interceptor sidecar or
a SaaS control plane. Kernel-level runtime enforcement, which only ever made
sense delivered through the agent, is retired with it.

## Consequences

### Supersedes

- **ADR-004 (SEP-1766 digest pinning) — partially superseded.** The
  digest-pinning *capability* lives on, in-process in core (core already
  enforces per-tenant digest pins on the call path). ADR-004's component split —
  `hangar-agent` extracts digests, `hangar-cloud` stores the approved allowlist —
  is void. The capability stays in core; the agent/cloud scoping is dropped.
- **ADR-005 (SEP-1763 interceptor compliance) — fully superseded.** The
  "`hangar-agent` as reference interceptor sidecar" roadmap is abandoned. Any
  continued SEP-1763 / interceptor alignment is in-process in core (see the
  experimental interceptor work,
  [mcp-hangar#488](https://github.com/mcp-hangar/mcp-hangar/issues/488)), not a
  sidecar runtime.
- **ADR-006 (Tetragon runtime enforcement) — fully superseded.** The enforcement
  pipeline it describes originated in Hangar Cloud (the MCP policy DSL) and
  `hangar-agent` (the policy compiler); with both retired, the kernel-level
  runtime-enforcement productization (Tetragon / KubeArmor / Falco backends) is
  retired as well. Governance is enforced in-process on the MCP call path, not
  via kernel hooks. If runtime enforcement is ever revived it will be a new
  decision on its own footing, not a continuation of this one.
- **ADR-009 (independent release topology) — partially superseded.** The "**four**
  independent release lanes" become **three**: core, operator image, and OCI Helm
  charts. The agent-image lane (the fourth lane) is retired and its open
  follow-up ("author the agent `release.yml`") is closed won't-do.

### Explicitly unaffected

Core multi-tenancy, front-door mode, per-tenant tool projection, OIDC trust, and
the `ToolAccessResolver` / `policy:write` machinery are live features unrelated
to the agent and are untouched. `policy:write` remains a valid permission, now
granted via the `admin` role. The durable `PolicyPushRejected` event is retained
(deprecated, producer-less) for event-replay compatibility.

## References

- [mcp-hangar#490](https://github.com/mcp-hangar/mcp-hangar/pull/490) — core code removal
- [helm-charts#43](https://github.com/mcp-hangar/helm-charts/pull/43) — agent chart removal
- [terraform-provider#13](https://github.com/mcp-hangar/terraform-provider/pull/13) — provider deprecation + archive
- Supersedes [ADR-004](ADR-004-sep-1766-digest-pinning.md), [ADR-005](ADR-005-sep-1763-interceptor-compliance.md), [ADR-006](ADR-006-tetragon.md), [ADR-009](ADR-009-independent-release-topology.md)
