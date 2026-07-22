# Governed Tasks (Task Relay)

Governance for asynchronous MCP tasks: Hangar relays an upstream-created task and interposes ownership, digest re-verification, a `task_id`-keyed audit chain, and a fail-closed mid-flight consent gate on its lifecycle -- without ever executing the task.

> **Landing in 2.0 / on the v2 preview.** Everything on this page ships on the v2 preview (prerelease `2.0.0a1`, `mcp==2.0.0b2`) and is **not** in released `1.6.0`. Tasks were promoted out of `mcp.server.experimental` into a first-class negotiated extension only in the SDK v2 beta, which is what makes governed relay buildable at all (see [ADR-014](../adr/ADR-014-tasks-relay-with-governance.md)). On `1.6.0` the observed behavior is still a clean `TaskRelayNotSupported` rejection of any upstream task handle.

## Overview

Synchronous `tools/call` has been the governed call-shape from the start: identity, digest pins, egress rules, and the audit stream all attach at the proxy chokepoint. Tasks are the one call-shape that was *dormant* -- an upstream can answer a call by handing back a `task_id` and finishing the work later, out of band, and until v2 that async path was ungoverned.

Governed Tasks close that gap. The model is **relay-with-governance, not executor**:

- Hangar **relays** a task an upstream created and **interposes governance** on its lifecycle -- `tasks/get`, `tasks/result`, `tasks/cancel`, `tasks/list`.
- Hangar does **not** create tasks, run a scheduler or GC, store results, or cross a worker-thread → main-loop execution bridge. There is no job runner. The proxy stays a proxy.

This is the same species distinction ADR-008 drew and [ADR-014](../adr/ADR-014-tasks-relay-with-governance.md) preserves: *Envoy does not run your cron jobs.* Hangar governs the call path of a task an upstream owns; it never becomes the thing that owns execution. What v2 lifts is only ADR-008's "*permanently* no relay" absolutism -- not the executor prohibition.

## The relay seam: every relayed task is locally known

The failure mode this design exists to exclude is the **dead handle**. Pass an upstream `task_id` straight through to the client and you have promised a handle you cannot answer for: a later `tasks/get` finds nothing, and the client gets a misleading "Task not found" for a task that is genuinely running upstream. ADR-008/`#368` papered over that with an honest rejection. ADR-014 replaces the rejection with a record.

On relaying an upstream `CreateTaskResult`, `GovernedTaskStore.relay_and_govern()` does registration and provenance as **one lock-held critical section** -- before the handle reaches the client:

1. Bind the owner (tenant + principal) from the request identity, cross-checked against the authorized owner.
2. Pin the tool digest carried on the synchronous invoke path.
3. Store the upstream-truth `Task` snapshot.
4. Emit the `TaskCreated` provenance head.

If the `TaskCreated` publish raises, the whole registration is rolled back -- zero governed state survives, no orphan binding, no headless provenance head. And because the record is written *before* the client ever sees the handle, a relayed `task_id` is **always** locally known. The dead-handle failure mode is structurally excluded, not merely tested against.

The store holds governance metadata **only** -- never a result payload, never execution state. Task ids are unique only per upstream, so every entry is keyed on the composite `TaskKey = (target_server_id, task_id)`; two upstreams may legitimately mint the same `task_id`.

## The four serving handlers

Once a task is relayed, a client follows up through four v2-native `tasks/*` request handlers registered on the low-level MCP server. Every handler is fail-closed, ownership-scoped, and upstream-truthful -- it never fabricates state.

| Handler | Wire method | What it does |
|---------|-------------|--------------|
| **Poll** | `tasks/get` | Relays to the owning upstream, syncs the local snapshot from the upstream status verbatim, returns it flat. A `working → completed` transition emits `TaskCompleted` exactly once. An `input_required` status triggers the [consent gate](#the-mid-flight-consent-gate-322). An upstream error returns the local snapshot unchanged. |
| **Fetch result** | `tasks/result` | **Re-verifies the pinned tool digest fail-closed** before relaying, then reconstructs the payload by validating the upstream `result` into `CallToolResult`. Digest drift fails the task and raises. |
| **Cancel** | `tasks/cancel` | Best-effort relay of `tasks/cancel`. Retires the entry **only** on a confirmed upstream cancellation (clean `result`, status `cancelled` or absent, no `error`); otherwise keeps the entry and returns its true current status. Confirmation emits `TaskCancelled` once. |
| **List (owner-only)** | `tasks/list` | Returns the caller's owned snapshots as a single page. The inner/upstream cursor is **never** forwarded -- it could identify another tenant's task -- so `nextCursor` is always absent. |

A client sends only a bare `task_id`. The handler resolves it to the composite key via `find_owned_key`, which is ownership-fail-closed: a `task_id` the caller does not own is indistinguishable from one that does not exist -- both raise the same `INVALID_PARAMS` "Task not found". No existence leak.

**Identity bridging.** On streamable-HTTP the transport runs the low-level request handler in a per-session task decoupled from the ASGI auth wrapper, so the ambient identity is not propagated in. Each handler bridges the authenticated principal off the FastMCP request context into `identity_context_var` for the duration -- exactly as the `hangar_call` batch path does (`#387`) -- and `asyncio.to_thread` copies that context into the worker thread where the (threading-locked) ledger runs. An absent principal leaves the caller unattributed, which is fail-closed downstream: an unattributed caller can only ever reach unattributed tasks.

## Per-task ownership and digest-pinned results

Authorization is fail-closed and runs on **every** public path through a single `authorize` chokepoint, delegating to the `TaskOwnershipRegistry`:

- **Reads** (`get_task`, `list_tasks`) return `None` / exclude the entry on denial -- a denied caller cannot tell "not found" from "not yours".
- **Mutations** (`update_snapshot`, `delete_task`, the terminal transitions) raise `McpError` `INVALID_PARAMS` with the same `"Task not found: <id>"` message. Denial never confirms existence.
- **Anonymous / system path:** with no identity bound the caller is `TaskOwner(None, None)` -- it can reach only unattributed entries, and can *never* reach a task owned by an attributed tenant.

The interesting half is **supply-chain integrity across the async boundary.** A synchronous call is governed against the tool schema digest the caller authorized. But a task finishes *later* -- and in that gap the tool's schema can drift. So the digest pinned at relay time is **re-verified fail-closed** every time a result is fetched: `tasks/result` calls `_verify_pinned_digest` before it relays. If the tool's current digest no longer matches the pin -- or the current schema cannot be verified at all -- the task is **failed**, a `DigestMismatchInTask` event is emitted, and an `McpError` is raised.

This is the ADR-008 "zombie" closed for the async case: a task can never complete against a tool contract the caller did not authorize. Digest drift *fails the task*; it does not merely refuse the result and leave a permanently-unavailable handle hanging.

## The `Task*` audit chain

`task_id → provenance` is an append-only event chain, built on ADR-002 event sourcing. Every event is keyed by `task_id` and carries `tenant_id` + `correlation_id`, threaded from the `TaskCreated` head so the whole chain shares one provenance thread:

| Event | Emitted when |
|-------|--------------|
| `TaskCreated` | The relay seam registers the task (the provenance head, written under the registration lock). |
| `TaskCompleted` | A `working → completed` transition is observed on poll -- deduplicated atomically, so repeated polls emit at most one. |
| `TaskCancelled` | A `tasks/cancel` is confirmed by the upstream -- deduplicated. |
| `TaskFailed` | The task is failed closed: digest drift, consent denial, or an evicted-but-still-live binding (`TaskFailed('evicted')`). |
| `TaskConsentDecided` | A mid-flight consent decision resolves -- granted or denied -- carrying the `input_key` and the `principal_id` that was prompted. |
| `DigestMismatchInTask` | Pinned-digest re-verification finds drift (paired with the `TaskFailed`). |

The full lifecycle of any relayed task is reconstructable from the event stream. This is the forensic non-repudiation the product thesis already sold for synchronous calls -- now extended to cover the async call-shape that was the last one left dark. (ADR-014 Decision 3 names `TaskInputRequired` in the lifecycle set as well; the emitted provenance on the v2-preview code path is the six events above.)

## The mid-flight consent gate (`#322`)

The consent gate is the first activated beneficiary of the relay seam, and the one genuinely interactive control in the stack.

When a relayed task's upstream status becomes `input_required`, the task is paused mid-flight waiting on a human decision. On the `2025-11-25` protocol there is no inbound `tasks/update` to carry that decision back, so `tasks/get` resolves it **synchronously, in-handler**:

1. The tenant is already authorized (structurally, above the gate).
2. A deterministic `input_key` is derived from the upstream's pending input request(s) -- stable across concurrent polls, so a second in-flight `tasks/get` maps to the same gate key and does not double-prompt.
3. The downstream client is **elicited** for consent over `ctx.session` -- a real, interactive human-in-the-loop prompt. If the client did not negotiate the elicitation capability, there is no back-channel to consent the caller: fail-closed immediately.
4. The gate opens **only on a confirmed accept** -- consent is obtained *before* the gate opens, so there is no open-then-decide race.
5. On accept, the answer is relayed upstream, the single-use consent is consumed only after a confirmed relay, `TaskConsentDecided(granted=True)` is recorded, and the post-input upstream status is re-synced.
6. On **any** non-accept outcome -- decline, cancel, no back-channel, elicitation error, missing capability -- the task is terminally **failed closed**, a best-effort `tasks/cancel` is relayed upstream, and `TaskConsentDecided(granted=False)` is recorded.

A paused task is therefore *never left hanging*. Every branch is terminal: it either proceeds with recorded consent or fails closed with a recorded denial. A transient upstream relay failure is the one recoverable case -- it discards the gate without consuming the consent and does not fail the task, so a retry re-elicits and completes.

## What this is not

Two distinctions the code enforces and the positioning depends on. Keep them exact.

**This is the only interactive consent flow -- the synchronous L7 gate is not.** The egress policy's `requireApproval` (see [Egress Policy](EGRESS_POLICY.md#l7-semantics)) **fails closed**: a gated synchronous `tools/call` is *blocked* pending an out-of-band approval. It is a hard gate, not an interactive approval queue -- nothing prompts a human and waits. The async consent gate here is the genuinely interactive path: it elicits a live human decision mid-flight and routes it back. Do not conflate them.

**Hangar relays and governs; it does not execute.** No scheduler, no result store, no GC/TTL correctness, no cancellation-race ownership, no worker → main-loop context bridge. Governance binds at the proxy/store seam on the request path -- the same seam that governs synchronous `tools/call` -- so the "one bug and governance silently does not bind" failure mode a background execution thread would introduce simply does not exist to break.

## Coming: the modern tasks protocol

The `2026-07-28` protocol handshake and the [SEP-2663](../adr/ADR-014-tasks-relay-with-governance.md) Tasks reshape change how mid-flight input is resolved: the client drives an inbound `tasks/update` carrying its input, rather than the server eliciting synchronously inside `tasks/get`. On that path the governed input handler is `tasks/update`, not `tasks/get`, and `tasks/list` is removed from the served surface.

This is **forward-compatible plumbing, not live behavior.** The serving surface tracks the negotiated protocol by registering each handler only while the SDK defines its type -- `tasks/list` only where `ListTasksResult` exists, the inbound `tasks/update` only where `UpdateTaskRequest` exists -- so the served methods follow the negotiated version without a version bump, and behavior on the `b2` beta is byte-identical. The modern branch stays unreachable on a `2025-11-25` session (the version probe is fail-safe to the pre-modern synchronous path). Treat `2026-07-28` / SEP-2663 as *coming*, never as shipped.

## Limitations and notes

- **v2 preview only.** Not in released `1.6.0`. The seam ships dark behind the `relay_tasks_enabled` kill-switch, retained for a fast per-deployment rollback.
- **Behavior is unchanged until an upstream emits a task.** Activation is per-upstream, on the first real task an upstream emits (ADR-014 Decision 5). A deployment whose upstreams never emit tasks observes no difference; the `tasks` capability is advertised at `INITIALIZE` only once the seam is live -- "do not advertise what does not run."
- **The ledger is in-memory.** An in-memory `task_id` mapping suffices for a relay; a durable/distributed task store remains the executor's problem and stays out of scope. The ownership registry and digest guard are TTL/LRU bounded, and an evicted still-live binding is failed closed (`TaskFailed('evicted')`) rather than silently vanishing.
- **Cancellation is best-effort relay.** Hangar forwards `tasks/cancel` and retires the entry only on confirmation; it takes on no cancellation-race ownership beyond the relay.
- **Consent requires a back-channel.** The mid-flight gate needs the downstream client to have negotiated the elicitation capability; without it, an `input_required` task fails closed.

## See also

- [ADR-014: Tasks are Relayed With Governance](../adr/ADR-014-tasks-relay-with-governance.md) -- the decision, the superseded ADR-008 absolutism, and the activation record.
- [ADR-008: Tasks Relay-Only](../adr/ADR-008-tasks-relay-only.md) -- the prior "relay-only, permanently" decision this supersedes in part.
- [Egress Policy](EGRESS_POLICY.md) -- the synchronous L7 governance, including the `requireApproval` gate this page contrasts with.
- [Tool Invocations with hangar_call](BATCH_INVOCATIONS.md) -- the synchronous call path whose identity-bridging pattern (`#387`) the task handlers reuse.
