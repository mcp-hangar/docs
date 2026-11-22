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
Not generated yet. The first `sync-conformance` run after core publishes its `conformance-pass-table` artifact from `main` fills this section.
<!-- END generated: conformance-pass-table -->
