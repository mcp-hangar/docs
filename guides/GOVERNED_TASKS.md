# Governed Tasks (Task Relay)

Governance for asynchronous MCP tasks: Hangar relays an upstream-created task and interposes ownership, digest re-verification, a `task_id`-keyed audit chain, and a fail-closed mid-flight consent gate on its lifecycle -- without ever executing the task.

> **v2 preview.** Everything here ships on the v2 preview and is **not** in released `1.6.2`, where any upstream task handle is still rejected `TaskRelayNotSupported`.
>
> The `relay_tasks_enabled` kill-switch defaults to **true**. It has been on, off and on again inside a week: activated 2026-07-22, turned off when the surface was found advertising a wire it did not serve, and turned back on once the SEP-2663 wire was actually served and verified end to end -- which is the condition [ADR-015](../adr/ADR-015-vendored-task-wire.md) Decision 5 set for reactivating it. Set it to `false` to restore the relay-only stance.

## Overview

Synchronous `tools/call` has been the governed call-shape from the start: identity, digest pins, egress rules, and the audit stream all attach at the proxy chokepoint. Tasks are the one call-shape that was *dormant* -- an upstream can answer a call by handing back a `task_id` and finishing the work later, out of band, and until v2 that async path was ungoverned.

Governed Tasks close that gap. The model is **relay-with-governance, not executor**:

- Hangar **relays** a task an upstream created and **interposes governance** on its lifecycle -- `tasks/get`, `tasks/update`, `tasks/cancel`.
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

## The three serving handlers

Once a task is relayed, a client follows up through the three `tasks/*` methods [SEP-2663](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2663) defines. Every handler is fail-closed, ownership-scoped, and upstream-truthful -- it never fabricates state.

| Handler | Wire method | What it does |
|---------|-------------|--------------|
| **Poll** | `tasks/get` | Relays to the owning upstream, syncs the local snapshot from the upstream status verbatim, and returns it flat with the outcome **inlined**. A `working → completed` transition emits `TaskCompleted` exactly once. An upstream error returns the local snapshot unchanged, with no outcome fields. |
| **Answer input** | `tasks/update` | The governed mid-flight input path -- see [the consent gate](#the-mid-flight-consent-gate-322). Relays the client's answers upstream verbatim and acknowledges empty. |
| **Cancel** | `tasks/cancel` | Best-effort relay. Retires the entry **only** on a confirmed upstream cancellation (clean `result`, status `cancelled` or absent, no `error`); otherwise keeps the entry with its true status. Confirmation emits `TaskCancelled` once. Acknowledges **empty**: cancellation is cooperative, so the ack must not claim an outcome the upstream never reported. |

`tasks/result` and `tasks/list` are **not served** -- SEP-2663 removes both. They are simply not registered, which is how they answer `-32601`; there is no separate rejection.

Removing `tasks/result` downstream does not mean Hangar stops *calling* it upstream. SEP-2663 inlines a completed task's payload on `tasks/get`, but an upstream on the older design still keeps it behind `tasks/result`, so Hangar fetches it on the client's behalf. Bridging the two generations is the relay's job; dropping both at once made every such payload unreachable until it was caught.

### Who is served, and what everyone else gets

SEP-2663 splits refusal into distinct codes, and the split is deliberate.

| Caller | Answer |
|---|---|
| 2026-07-28 client declaring `io.modelcontextprotocol/tasks` | served |
| 2026-07-28 client that did not declare it | `-32021` + machine-readable `requiredCapabilities` |
| 2025-11-25 or older connection | `-32601` -- the methods do not exist there |
| missing or contradictory `Mcp-Name` header | `-32020` |
| unknown or unowned task id | `-32602` |

A modern client can fix its declaration and retry, so it is told *what* to declare. A legacy connection cannot, so for it the methods simply do not exist. The ladder runs version → routing header → capability, and every rung refuses before the request reaches the upstream.

`Mcp-Name: <taskId>` is mandatory on all three methods (SEP-2663 via SEP-2243) so an intermediary can route a poll without parsing the body. Hangar enforces presence, not just agreement: a header that is only *sometimes* there cannot be routed on. The set is exported as `NAME_BEARING_TASK_METHODS` for the operator's L7 selector.

**Discovery.** The extension is advertised under `capabilities.extensions`, not `capabilities.tasks`. The 2026-07-28 `ServerCapabilities` has no `tasks` field -- SEP-2663 moved Tasks out of the core set -- so a server advertising it there has the entry sieved out of its own `server/discover` and becomes undiscoverable to exactly the clients it serves.

A client sends only a bare `task_id`. The handler resolves it to the composite key via `find_owned_key`, which is ownership-fail-closed: a `task_id` the caller does not own is indistinguishable from one that does not exist -- both raise the same `INVALID_PARAMS` "Task not found". No existence leak.

**Identity bridging.** On streamable-HTTP the transport runs the low-level request handler in a per-session task decoupled from the ASGI auth wrapper, so the ambient identity is not propagated in. Each handler bridges the authenticated principal off the FastMCP request context into `identity_context_var` for the duration -- exactly as the `hangar_call` batch path does (`#387`) -- and `asyncio.to_thread` copies that context into the worker thread where the (threading-locked) ledger runs. An absent principal leaves the caller unattributed, which is fail-closed downstream: an unattributed caller can only ever reach unattributed tasks.

## Per-task ownership and digest-pinned results

Authorization is fail-closed and runs on **every** public path through a single `authorize` chokepoint, delegating to the `TaskOwnershipRegistry`:

- **Reads** (`get_task`, `list_tasks`) return `None` / exclude the entry on denial -- a denied caller cannot tell "not found" from "not yours".
- **Mutations** (`update_snapshot`, `delete_task`, the terminal transitions) raise `McpError` `INVALID_PARAMS` with the same `"Task not found: <id>"` message. Denial never confirms existence.
- **Anonymous / system path:** with no identity bound the caller is `TaskOwner(None, None)` -- it can reach only unattributed entries, and can *never* reach a task owned by an attributed tenant.

The interesting half is **supply-chain integrity across the async boundary.** A synchronous call is governed against the tool schema digest the caller authorized. But a task finishes *later* -- and in that gap the tool's schema can drift. So the digest pinned at relay time is **re-verified fail-closed** before any outcome is handed over: `tasks/get` calls `_verify_pinned_digest` before it fetches or inlines a payload. It guarded `tasks/result` until SEP-2663 removed that method; the check moved with the payload rather than retiring alongside it, because `tasks/get` is now the only path by which a result reaches a caller. If the tool's current digest no longer matches the pin -- or the current schema cannot be verified at all -- the task is **failed**, a `DigestMismatchInTask` event is emitted, and an `McpError` is raised.

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

The consent gate is the first activated beneficiary of the relay seam: the point where a task that pauses for input is governed rather than merely proxied.

When a relayed task's upstream status becomes `input_required`, the task is paused mid-flight waiting on the caller. The client sees what is wanted -- the snapshot carries the upstream's `inputRequests` map -- and answers it by driving an inbound `tasks/update`. **That update is the consent**, and it is where governance binds:

1. The tenant is authorized first, structurally above the gate. A foreign tenant is refused before anything opens or relays.
2. A deterministic `input_key` is derived from the upstream's pending input request(s), stable across concurrent polls.
3. The gate opens **before** the answer reaches the upstream, and the single-use consent is **consumed only after a confirmed relay**.
4. `TaskConsentDecided(granted=True)` records the decision with the principal that made it.
5. A transient upstream refusal discards the gate **without** consuming it and does not fail the task -- a retry re-drives the update and completes.

The acknowledgement is empty; the client polls `tasks/get` for the resulting state.

> **The interactive elicitation flow is gone.** Until 2026-07-28 Hangar resolved a pause by prompting the client with `elicitation/create` *inside* the `tasks/get` that observed it, failing closed on decline, cancel, missing capability or any elicitation error. That belonged to the 2025-11-25 wire, which Hangar no longer serves. Consent is still governed and still fail-closed -- it is gated on the update rather than on a prompt -- but nothing prompts a human on Hangar's initiative any more.

## What this is not

Two distinctions the code enforces and the positioning depends on. Keep them exact.

**Neither gate prompts a human.** The egress policy's `requireApproval` (see [Egress Policy](EGRESS_POLICY.md#l7-semantics)) **fails closed**: a gated synchronous `tools/call` is *blocked* pending an out-of-band approval. The async gate here is fail-closed too, on a decision the client volunteers by driving `tasks/update`. Hangar used to be the interactive one -- it elicited a live decision mid-poll -- and on the SEP-2663 wire it no longer does. Do not describe either as an interactive approval queue.

**Hangar relays and governs; it does not execute.** No scheduler, no result store, no GC/TTL correctness, no cancellation-race ownership, no worker → main-loop context bridge. Governance binds at the proxy/store seam on the request path -- the same seam that governs synchronous `tools/call` -- so the "one bug and governance silently does not bind" failure mode a background execution thread would introduce simply does not exist to break.

## The modern tasks protocol is what ships

The `2026-07-28` generation and the SEP-2663 reshape are **served**, not pending. That is a correction: this page previously described them as forward-compatible plumbing that would light up on its own.

The mechanism it described does not work. The serving surface was meant to track the SDK by registering each handler only while the SDK defined its type -- `tasks/list` while `ListTasksResult` existed, `tasks/update` once `UpdateTaskRequest` arrived. Those probes watch `mcp_types`, which carries the **SEP-1686** generation that 2026-07-28 removed from the core spec. Measured across `mcp==2.0.0b2`, `2.0.0rc1` and the stable `2.0.0`: all 29 `Task*` classes are field-for-field identical, while the module around them was edited throughout. A frozen region inside a moving beta could have been a snapshot mid-migration; one that ships unchanged in a **major** is a decision -- so the probes were latches that could never trip -- `tasks/list` was always served and `tasks/update` never was.

The wire is therefore **vendored** in `mcp_hangar/tasks_wire.py`, tracking SEP-2663 and [python-sdk#3005](https://github.com/modelcontextprotocol/python-sdk/pull/3005) rather than the SDK's frozen types. Flat `CreateTaskResult` with `resultType`, `ttlMs` / `pollIntervalMs`, the outcome inlined on `tasks/get`. See [ADR-015](../adr/ADR-015-vendored-task-wire.md), which records the rule that generalises past Tasks: *a capability probe is a hedge only when the probed module can still change.*

## Limitations and notes

- **v2 preview only.** Not in released `1.6.2`. `relay_tasks_enabled` defaults to **true** on the preview and is retained as a per-deployment rollback. What to check before changing it is not whether the surface is wanted, but whether the served wire matches what is advertised -- that mismatch is what took it out once already.
- **Behavior is unchanged until an upstream emits a task.** Activation is per-upstream, on the first real task an upstream emits (ADR-014 Decision 5). A deployment whose upstreams never emit tasks observes no difference; the extension is advertised on `server/discover` only once the seam is live -- "do not advertise what does not run."
- **The ledger is in-memory.** An in-memory `task_id` mapping suffices for a relay; a durable/distributed task store remains the executor's problem and stays out of scope. The ownership registry and digest guard are TTL/LRU bounded, and an evicted still-live binding is failed closed (`TaskFailed('evicted')`) rather than silently vanishing.
- **Cancellation is best-effort relay.** Hangar forwards `tasks/cancel` and retires the entry only on confirmation; it takes on no cancellation-race ownership beyond the relay.
- **The client must be able to speak the wire at all.** `tasks/*` are reachable only on a 2026-07-28 connection with the extension declared. The `initialize` handshake cannot negotiate that generation -- it tops out at `2025-11-25` -- so a client reaches this surface only on the per-request-envelope path, and only if it stamps `Mcp-Name` per request.

## See also

- [ADR-014: Tasks are Relayed With Governance](../adr/ADR-014-tasks-relay-with-governance.md) -- the decision, the superseded ADR-008 absolutism, and the activation record.
- [ADR-015: The Tasks Wire is Vendored](../adr/ADR-015-vendored-task-wire.md) -- why the served shapes are not the SDK's, and the probe rule that generalises.
- [ADR-008: Tasks Relay-Only](../adr/ADR-008-tasks-relay-only.md) -- the prior "relay-only, permanently" decision this supersedes in part.
- [Egress Policy](EGRESS_POLICY.md) -- the synchronous L7 governance, including the `requireApproval` gate this page contrasts with.
- [Tool Invocations with hangar_call](BATCH_INVOCATIONS.md) -- the synchronous call path whose identity-bridging pattern (`#387`) the task handlers reuse.
