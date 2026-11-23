---
title: MCP Conformance
description: The official MCP conformance suite's verdict on Hangar as a server, in the egress and front_door topologies, and as a client, on protocol 2026-07-28 and 2025-11-25, generated from core's CI.
sidebar_label: Conformance
sidebar_order: 6
---

Hangar's own tests assert what its maintainers believe the protocol requires. The official suite, `@modelcontextprotocol/conformance`, asserts what the specification's maintainers say it requires. Core's `MCP Conformance` workflow runs that suite against Hangar on every pull request that touches the gateway, on every push to `main` and weekly. Its `Conformance` check fails on any result its baseline does not expect.

## What is run

| Role | Revision | What is under test |
| --- | --- | --- |
| Server | 2026-07-28 | `serve --http` in the default `egress` topology, one subprocess backend, streamable HTTP |
| Server | 2025-11-25 | The same gateway, judged on the revision it still serves for older clients |
| Client | 2026-07-28 | Hangar's upstream connection: the suite's test server is registered as a remote upstream and called through the gateway |
| Client | 2025-11-25 | The same, on the older revision |
| Server, front_door | 2026-07-28 | A `front_door` gateway with auth on and the suite's reference server behind it, judged as one authenticated caller sees it |
| Server, front_door | 2025-11-25 | The same gateway, judged on the older revision |

The page shows the tables in that order.

### The front_door topology

The egress server tables judge a gateway whose only backend serves a handful of math tools. A scenario that needs the suite's own fixtures (an image tool, a prompt, a resource, an eliciting tool) cannot pass there, and its egress line says what the front_door run found instead.

The front_door tables judge the topology that serves upstream tools under their own names. `serve --http` runs with `tool_access.mode: front_door` and authentication on, with one API-key principal holding the `developer` role. Its only upstream is the suite's reference everything-server, taken from the conformance repository at the commit the pinned suite version was built from. Every tool that server lists is projected flat. A front door serves an anonymous caller no tool, and the suite's `server` command cannot present a credential. So a loopback proxy adds the principal's `X-API-Key` header to every request and changes nothing else. The proxy is test plumbing; what is judged is the gateway answering an authenticated caller. Each front_door table names the reference server's commit next to the suite version.

Two things about that setup shape what the front_door tables can judge:

- Hangar opens the reference server with `upstream_protocol: auto` and finds it serves 2026-07-28. So it speaks to it statelessly on both revisions. On 2025-11-25 that upstream asks for sampling and elicitation with an input-required result rather than a server-to-client request, and has no `resources/subscribe` to relay.
- The front door namespaces every resource URI it hands out as `hangar://<upstream>/<the upstream's URI>`. A scenario that reads the reference server's fixed URI directly therefore gets an unknown resource. This is a recorded design decision, not a failed read.

The reference server alone passes every scenario either revision scores, with one exception: on 2026-07-28 it warns on its own in `input-required-result-validate-input`. So a non-pass in a front_door table is Hangar's (`Tracked by` names the issue), a recorded decision, or a fixture the reference server lacks at that commit.

Not covered: stdio. The suite's `server` command reaches a server only through a URL, and its client scenarios serve HTTP, so neither role is judged over stdio. This was accepted in [mcp-hangar#1902](https://github.com/mcp-hangar/mcp-hangar/issues/1902) rather than bridged, and core's ecosystem watch reports when the suite can reach a stdio peer.

## How to read the tables

Each table is one run of one role on one revision. A row is one scenario of the suite, and its checks are counted the way the suite counts them: a `FAILURE` or a `WARNING` fails the scenario, while a `SKIPPED` check (the suite had nothing to judge, for example because the client never sent that request) counts neither way and has its own column.

- `pass`: no check of the scenario failed.
- `known`: a check failed and the scenario's baseline in core lists it, so the run is still green.
- `stale`: no check failed but the baseline still lists the scenario. The suite fails such a run until the line is deleted.
- `REGRESSION`: a check failed and nothing expects it. The run is red.
- `pass, not scored: <reason>` or `fail, not scored: <reason>`: the suite runs the scenario for this revision but does not score it, so it moves neither the pass count nor the run's result. The list and the reasons are the suite's own frozen `requirements/<revision>.yaml`: `extension` (an optional protocol extension), `pending` (the suite's own reference fixture cannot pass it yet) or `added-after-release` (added to the suite after the revision shipped). The client 2025-11-25 run selects its scenarios by version rather than by that file, so every row in it is scored.

`Tracked by` names the issue (`#N`, in [mcp-hangar](https://github.com/mcp-hangar/mcp-hangar/issues)) or the specification change (`SEP-N`) that the baseline line cites. Each table names the suite version and the core commit it was run against.

## Pass table

<!-- BEGIN generated: conformance-pass-table — regenerated by scripts/sync_conformance_table.py (sync-conformance workflow) from core's conformance-pass-table artifact. Do not hand-edit. -->
Generated from [this run](https://github.com/mcp-hangar/mcp-hangar/actions/runs/45079585886) of core at `fbcc2423724a` on `main`.

### Server, 2026-07-28

7 of 37 scored scenarios pass; 30 are known failures in `baseline-2026-07-28.yml`; 0 are regressions. 13 more ran but are not scored for this revision.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `caching` | 4 | 3 | 1 | known | #2307 |
| `completion-complete` | 1 | 1 | 0 | known | #2307 |
| `dns-rebinding-protection` | 2 | 0 | 0 | pass | |
| `http-custom-header-server-validation` | 1 | 5 | 0 | fail, not scored: pending | #2318 |
| `http-header-validation` | 14 | 0 | 0 | pass, not scored: pending | |
| `input-required-result-basic-elicitation` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-basic-list-roots` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-basic-sampling` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-capability-check` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-ignore-extra-params` | 2 | 0 | 0 | pass | |
| `input-required-result-missing-input-response` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-multi-round` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-multiple-input-requests` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-non-tool-request` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-request-state` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-result-type` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-tampered-state` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-unsupported-methods` | 2 | 0 | 0 | pass | |
| `input-required-result-validate-input` | 2 | 1 | 0 | known | #2313 |
| `json-schema-2020-12` | 1 | 1 | 0 | fail, not scored: pending | #2307 |
| `prompts-get-embedded-resource` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-simple` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-with-args` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-with-image` | 1 | 1 | 0 | known | #2307 |
| `prompts-list` | 1 | 1 | 0 | known | #2307 |
| `resources-list` | 1 | 1 | 0 | known | #2307 |
| `resources-read-binary` | 1 | 1 | 0 | known | #1025 |
| `resources-read-text` | 1 | 1 | 0 | known | #1025 |
| `resources-templates-read` | 1 | 1 | 0 | known | #1025 |
| `sep-2164-resource-not-found` | 2 | 2 | 0 | known | #2316 |
| `server-sse-multiple-streams` | 2 | 0 | 0 | pass | |
| `server-stateless` | 23 | 2 | 5 | known | #2318 |
| `tasks-capability-negotiation` | 4 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-dispatch-and-envelope` | 7 | 2 | 0 | fail, not scored: extension | #2318 |
| `tasks-lifecycle` | 2 | 7 | 0 | fail, not scored: extension | #2318 |
| `tasks-mrtr-composition` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-mrtr-input` | 1 | 3 | 0 | fail, not scored: extension | #2318 |
| `tasks-request-headers` | 2 | 3 | 0 | fail, not scored: extension | #2318 |
| `tasks-request-state-removal` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-required-task-error` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-status-notifications` | 0 | 0 | 1 | pass, not scored: extension | #2318 |
| `tasks-wire-fields` | 1 | 3 | 0 | fail, not scored: extension | #2318 |
| `tools-call-audio` | 1 | 1 | 0 | known | #2307 |
| `tools-call-embedded-resource` | 1 | 1 | 0 | known | #2307 |
| `tools-call-error` | 2 | 0 | 0 | pass | |
| `tools-call-image` | 1 | 1 | 0 | known | #2307 |
| `tools-call-mixed-content` | 1 | 1 | 0 | known | #2307 |
| `tools-call-simple-text` | 2 | 0 | 0 | pass | |
| `tools-call-with-progress` | 1 | 1 | 0 | known | #2314 |
| `tools-list` | 4 | 0 | 0 | pass | |

### Server, 2025-11-25

6 of 30 scored scenarios pass; 24 are known failures in `baseline-2025-11-25.yml`; 0 are regressions. 3 more ran but are not scored for this revision.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `completion-complete` | 1 | 1 | 0 | known | #2307 |
| `dns-rebinding-protection` | 2 | 0 | 0 | pass | |
| `elicitation-sep1034-defaults` | 1 | 1 | 0 | known | #2313 |
| `elicitation-sep1330-enums` | 1 | 1 | 0 | known | #2313 |
| `json-schema-2020-12` | 1 | 1 | 0 | fail, not scored: pending | #2307 |
| `logging-set-level` | 1 | 1 | 0 | known | SEP-2575, SEP-2577 |
| `ping` | 2 | 0 | 0 | pass | |
| `prompts-get-embedded-resource` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-simple` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-with-args` | 1 | 1 | 0 | known | #2307 |
| `prompts-get-with-image` | 1 | 1 | 0 | known | #2307 |
| `prompts-list` | 1 | 1 | 0 | known | #2307 |
| `resources-list` | 1 | 1 | 0 | known | #2307 |
| `resources-read-binary` | 1 | 1 | 0 | known | #1025 |
| `resources-read-text` | 1 | 1 | 0 | known | #1025 |
| `resources-subscribe` | 1 | 1 | 0 | known | #2317 |
| `resources-templates-read` | 1 | 1 | 0 | known | #1025 |
| `resources-unsubscribe` | 1 | 1 | 0 | known | #2317 |
| `server-initialize` | 3 | 0 | 0 | pass | |
| `server-session-lifecycle` | 1 | 0 | 0 | pass, not scored: added-after-release | |
| `server-sse-multiple-streams` | 0 | 1 | 0 | known | #877 |
| `server-sse-polling` | 4 | 4 | 0 | fail, not scored: pending | #2232 |
| `tools-call-audio` | 1 | 1 | 0 | known | #2307 |
| `tools-call-elicitation` | 1 | 1 | 0 | known | #2313 |
| `tools-call-embedded-resource` | 1 | 1 | 0 | known | #2307 |
| `tools-call-error` | 2 | 0 | 0 | pass | |
| `tools-call-image` | 1 | 1 | 0 | known | #2307 |
| `tools-call-mixed-content` | 1 | 1 | 0 | known | #2307 |
| `tools-call-sampling` | 1 | 1 | 0 | known | #2313 |
| `tools-call-simple-text` | 2 | 0 | 0 | pass | |
| `tools-call-with-logging` | 1 | 1 | 0 | known | SEP-2575 |
| `tools-call-with-progress` | 1 | 1 | 0 | known | #2314 |
| `tools-list` | 3 | 0 | 0 | pass | |

### Client, 2026-07-28

6 of 32 scored scenarios pass; 26 are known failures in `baseline-client-2026-07-28.yml`; 0 are regressions. 7 more ran but are not scored for this revision.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `auth/authorization-server-migration` | 6 | 1 | 0 | known | #2012 |
| `auth/basic-cimd` | 4 | 1 | 0 | known | #2012 |
| `auth/client-credentials-basic` | 4 | 1 | 0 | fail, not scored: extension | #2012 |
| `auth/client-credentials-jwt` | 4 | 1 | 0 | fail, not scored: extension | #2012 |
| `auth/dpop` | 4 | 3 | 0 | fail, not scored: extension | #2012 |
| `auth/dpop-nonce` | 4 | 5 | 0 | fail, not scored: extension | #2012 |
| `auth/enterprise-managed-authorization` | 4 | 2 | 0 | fail, not scored: extension | #2012 |
| `auth/iss-normalized` | 4 | 1 | 0 | known | #2012 |
| `auth/iss-not-advertised` | 4 | 1 | 0 | known | #2012 |
| `auth/iss-supported` | 4 | 1 | 0 | known | #2012 |
| `auth/iss-supported-missing` | 4 | 1 | 0 | known | #2012 |
| `auth/iss-unexpected` | 4 | 1 | 0 | known | #2012 |
| `auth/iss-wrong-issuer` | 4 | 1 | 0 | known | #2012 |
| `auth/metadata-default` | 4 | 7 | 0 | known | #2012 |
| `auth/metadata-issuer-mismatch` | 4 | 1 | 0 | known | #2012 |
| `auth/metadata-var1` | 4 | 7 | 0 | known | #2012 |
| `auth/metadata-var2` | 4 | 6 | 0 | known | #2012 |
| `auth/metadata-var3` | 4 | 6 | 0 | known | #2012 |
| `auth/offline-access-not-supported` | 4 | 1 | 0 | known | #2012 |
| `auth/offline-access-scope` | 5 | 1 | 0 | known | #2012 |
| `auth/pre-registration` | 4 | 1 | 0 | known | #2012 |
| `auth/resource-mismatch` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-from-scopes-supported` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-from-www-authenticate` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-omitted-when-undefined` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-retry-limit` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-step-up` | 4 | 3 | 0 | known | #2012 |
| `auth/token-endpoint-auth-basic` | 4 | 3 | 0 | known | #2012 |
| `auth/token-endpoint-auth-none` | 4 | 3 | 0 | known | #2012 |
| `auth/token-endpoint-auth-post` | 4 | 3 | 0 | known | #2012 |
| `auth/wif-jwt-bearer` | 4 | 1 | 0 | fail, not scored: extension | #2012 |
| `http-custom-headers` | 18 | 0 | 0 | pass | |
| `http-invalid-tool-headers` | 12 | 0 | 0 | pass | |
| `http-standard-headers` | 3 | 0 | 8 | pass | |
| `json-schema-2020-12-preservation` | 9 | 0 | 0 | pass, not scored: added-after-release | |
| `json-schema-ref-no-deref` | 1 | 0 | 0 | pass | |
| `request-metadata` | 5 | 0 | 3 | pass | |
| `sep-2322-client-request-state` | 0 | 5 | 0 | known | #2010 |
| `tools_call` | 2 | 0 | 0 | pass | |

### Client, 2025-11-25

4 of 19 scenarios pass; 15 are known failures in `baseline-client-2025-11-25.yml`; 0 are regressions.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `auth/basic-cimd` | 4 | 1 | 0 | known | #2012 |
| `auth/metadata-default` | 4 | 7 | 0 | known | #2012 |
| `auth/metadata-var1` | 4 | 7 | 0 | known | #2012 |
| `auth/metadata-var2` | 4 | 6 | 0 | known | #2012 |
| `auth/metadata-var3` | 4 | 6 | 0 | known | #2012 |
| `auth/pre-registration` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-from-scopes-supported` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-from-www-authenticate` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-omitted-when-undefined` | 4 | 1 | 0 | known | #2012 |
| `auth/scope-retry-limit` | 8 | 1 | 0 | known | #2012 |
| `auth/scope-step-up` | 8 | 2 | 0 | known | #2012 |
| `auth/token-endpoint-auth-basic` | 4 | 3 | 0 | known | #2012 |
| `auth/token-endpoint-auth-none` | 4 | 3 | 0 | known | #2012 |
| `auth/token-endpoint-auth-post` | 4 | 3 | 0 | known | #2012 |
| `elicitation-sep1034-client-defaults` | 16 | 6 | 0 | known | #2013 |
| `initialize` | 2 | 0 | 0 | pass | |
| `json-schema-2020-12-preservation` | 9 | 0 | 0 | pass | |
| `sse-retry` | 17 | 0 | 0 | pass | |
| `tools_call` | 2 | 0 | 0 | pass | |

### Server, front_door, 2026-07-28

20 of 37 scored scenarios pass; 17 are known failures in `baseline-front-door-2026-07-28.yml`; 0 are regressions. 13 more ran but are not scored for this revision.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`, the suite's reference everything-server at `f44482ba17df` behind it.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `caching` | 8 | 0 | 0 | pass | |
| `completion-complete` | 2 | 0 | 0 | pass | |
| `dns-rebinding-protection` | 2 | 0 | 0 | pass | |
| `http-custom-header-server-validation` | 1 | 5 | 0 | fail, not scored: pending | #2318 |
| `http-header-validation` | 14 | 0 | 0 | pass, not scored: pending | |
| `input-required-result-basic-elicitation` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-basic-list-roots` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-basic-sampling` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-capability-check` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-ignore-extra-params` | 2 | 0 | 0 | pass | |
| `input-required-result-missing-input-response` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-multi-round` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-multiple-input-requests` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-non-tool-request` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-request-state` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-result-type` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-tampered-state` | 1 | 1 | 0 | known | #2313 |
| `input-required-result-unsupported-methods` | 2 | 0 | 0 | pass | |
| `input-required-result-validate-input` | 2 | 1 | 0 | known | #2313, #2318 |
| `json-schema-2020-12` | 8 | 0 | 0 | pass, not scored: pending | |
| `prompts-get-embedded-resource` | 2 | 0 | 0 | pass | |
| `prompts-get-simple` | 2 | 0 | 0 | pass | |
| `prompts-get-with-args` | 2 | 0 | 0 | pass | |
| `prompts-get-with-image` | 2 | 0 | 0 | pass | |
| `prompts-list` | 2 | 0 | 0 | pass | |
| `resources-list` | 2 | 0 | 0 | pass | |
| `resources-read-binary` | 1 | 1 | 0 | known | #1025 |
| `resources-read-text` | 1 | 1 | 0 | known | #1025 |
| `resources-templates-read` | 1 | 1 | 0 | known | #1025 |
| `sep-2164-resource-not-found` | 2 | 2 | 0 | known | #2316 |
| `server-sse-multiple-streams` | 2 | 0 | 0 | pass | |
| `server-stateless` | 28 | 2 | 0 | known | #2318 |
| `tasks-capability-negotiation` | 3 | 2 | 0 | fail, not scored: extension | #2318 |
| `tasks-dispatch-and-envelope` | 4 | 5 | 0 | fail, not scored: extension | #2318 |
| `tasks-lifecycle` | 1 | 8 | 0 | fail, not scored: extension | #2318 |
| `tasks-mrtr-composition` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-mrtr-input` | 1 | 3 | 0 | fail, not scored: extension | #2318 |
| `tasks-request-headers` | 2 | 3 | 0 | fail, not scored: extension | #2318 |
| `tasks-request-state-removal` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-required-task-error` | 1 | 1 | 0 | fail, not scored: extension | #2318 |
| `tasks-status-notifications` | 0 | 0 | 1 | pass, not scored: extension | |
| `tasks-wire-fields` | 1 | 3 | 0 | fail, not scored: extension | #2318 |
| `tools-call-audio` | 2 | 0 | 0 | pass | |
| `tools-call-embedded-resource` | 2 | 0 | 0 | pass | |
| `tools-call-error` | 2 | 0 | 0 | pass | |
| `tools-call-image` | 2 | 0 | 0 | pass | |
| `tools-call-mixed-content` | 2 | 0 | 0 | pass | |
| `tools-call-simple-text` | 2 | 0 | 0 | pass | |
| `tools-call-with-progress` | 2 | 0 | 0 | pass | |
| `tools-list` | 4 | 0 | 0 | pass | |

### Server, front_door, 2025-11-25

18 of 30 scored scenarios pass; 12 are known failures in `baseline-front-door-2025-11-25.yml`; 0 are regressions. 3 more ran but are not scored for this revision.

Run with suite `@modelcontextprotocol/conformance@0.2.0-alpha.12`, Hangar at `fbcc2423724a`, the suite's reference everything-server at `f44482ba17df` behind it.

| Scenario | Checks passed | Checks failed | Checks skipped | Result | Tracked by |
| --- | --- | --- | --- | --- | --- |
| `completion-complete` | 2 | 0 | 0 | pass | |
| `dns-rebinding-protection` | 2 | 0 | 0 | pass | |
| `elicitation-sep1034-defaults` | 1 | 1 | 0 | known | #2313 |
| `elicitation-sep1330-enums` | 1 | 1 | 0 | known | #2313 |
| `json-schema-2020-12` | 8 | 0 | 0 | pass, not scored: pending | |
| `logging-set-level` | 1 | 1 | 0 | known | SEP-2575, SEP-2577 |
| `ping` | 2 | 0 | 0 | pass | |
| `prompts-get-embedded-resource` | 2 | 0 | 0 | pass | |
| `prompts-get-simple` | 2 | 0 | 0 | pass | |
| `prompts-get-with-args` | 2 | 0 | 0 | pass | |
| `prompts-get-with-image` | 2 | 0 | 0 | pass | |
| `prompts-list` | 2 | 0 | 0 | pass | |
| `resources-list` | 2 | 0 | 0 | pass | |
| `resources-read-binary` | 1 | 1 | 0 | known | #1025 |
| `resources-read-text` | 1 | 1 | 0 | known | #1025 |
| `resources-subscribe` | 1 | 1 | 0 | known | #2317 |
| `resources-templates-read` | 1 | 1 | 0 | known | #1025 |
| `resources-unsubscribe` | 1 | 1 | 0 | known | #2317 |
| `server-initialize` | 3 | 0 | 0 | pass | |
| `server-session-lifecycle` | 1 | 0 | 0 | pass, not scored: added-after-release | |
| `server-sse-multiple-streams` | 0 | 1 | 0 | known | #877 |
| `server-sse-polling` | 5 | 3 | 0 | fail, not scored: pending | #877, #2232 |
| `tools-call-audio` | 2 | 0 | 0 | pass | |
| `tools-call-elicitation` | 1 | 1 | 0 | known | #2313 |
| `tools-call-embedded-resource` | 2 | 0 | 0 | pass | |
| `tools-call-error` | 2 | 0 | 0 | pass | |
| `tools-call-image` | 2 | 0 | 0 | pass | |
| `tools-call-mixed-content` | 2 | 0 | 0 | pass | |
| `tools-call-sampling` | 1 | 1 | 0 | known | #2313 |
| `tools-call-simple-text` | 2 | 0 | 0 | pass | |
| `tools-call-with-logging` | 1 | 1 | 0 | known | SEP-2575 |
| `tools-call-with-progress` | 2 | 0 | 0 | pass | |
| `tools-list` | 3 | 0 | 0 | pass | |
<!-- END generated: conformance-pass-table -->
