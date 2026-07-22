# ADR-014: Tasks are Relayed With Governance -- Hangar Interposes Task Lifecycle, It Still Does Not Execute

**Status:** Accepted; **Activated 2026-07-22** (see [Activation](#activation))
**Date:** 2026-07-20
**Authors:** MCP Hangar Team
**Supersedes:** ADR-008 (in part) -- lifts Decision 1's "relay-only *permanently*" absolutism and Decision 3's "do not build the relay yet"; carries ADR-008's other decisions forward unchanged.
**Related:** ADR-002 (event sourcing), ADR-004 (digest pinning), ADR-009 (release topology, "do not advertise what does not run").

## Context

ADR-008 (2026-07-02) decided task governance is **relay-only, permanently**: Hangar
would never create tasks (executor), and even the *relay* was deferred until **both**
of two triggers held -- (a) a real upstream emitting tasks in production, **and**
(b) the MCP task API graduating out of `mcp.server.experimental`. Until then the only
implemented behavior is an explicit `TaskRelayNotSupported` rejection of any upstream
task handle (PR `#368`), replacing an accidental "Task not found" dead-handle. The full
per-task governance stack was built, unit-tested, and left **dormant**.

Two facts have changed since:

1. **Trigger (b) is met.** The SDK v2 beta (`mcp==2.0.0b2`, verified in the `#547`
   spike) **promotes Tasks out of `experimental` into a first-class, negotiated
   protocol extension**: `CreateTask` / `GetTask` / `GetTaskPayload` (polling) /
   `ListTasks` / `CancelTask`, `TaskStatusNotification`, full capability negotiation
   (`ServerTasksCapability`, `TasksCall/List/Cancel/Sampling/Elicitation…`), and a
   server extension registry. The API ADR-008 called too churny to build against is
   now stable and discoverable.

2. **The governance stack is built and stranded.** `GovernedTaskStore` (ownership +
   digest re-verification, fail-closed), `TaskOwnershipRegistry` (`#319`),
   `TaskDigestGuard` (`#320`), the five `Task*` lifecycle audit events (`#321`, on
   `main`), and the `TaskConsentGate` primitive (`#322`, built + tested, wired to
   nothing) all exist. `#322` (p1-high, mid-flight consent) is **product-blocked on
   this ADR** -- its own status names "a ratified product/API decision to produce or
   relay MCP tasks" as the unblocker.

ADR-008's own text pre-committed the downstream decisions "for when the relay is built"
and said that when the triggers hold "the relay is weeks, not quarters." This ADR is
that moment for trigger (b). It does **not** reopen the executor question -- Hangar
still does not run jobs.

## Decision

1. **Relay-with-governance, not executor.** Hangar **relays** upstream-created tasks
   and **interposes governance** on their lifecycle. It still does not create tasks,
   own background execution, run a scheduler/GC, or cross a worker-thread -> main-loop
   execution bridge. ADR-008's species distinction ("Envoy does not run your cron
   jobs") is preserved; only its "*permanently* no relay" absolutism is lifted.

2. **Every relayed task is locally governed the instant it is relayed.** On relaying an
   upstream `CreateTaskResult`, Hangar creates a `GovernedTaskStore` entry and emits a
   `TaskCreated` event **before** the handle reaches the client. A relayed `task_id` is
   therefore always locally known -- the dead-handle failure mode ADR-008/`#368` fixed
   by rejection **cannot recur**, because rejection is replaced by a tracked record,
   not by pass-through.

3. **`task_id` -> provenance is an append-only event chain.** Built on ADR-002 event
   sourcing: the `Task*` lifecycle events (`TaskCreated`, `TaskInputRequired`,
   `TaskCompleted`, `TaskFailed`, `TaskCancelled`; `#321`) plus `DigestMismatchInTask*`
   (`#320`), all keyed by `task_id` and carrying `tenant_id` + `correlation_id`. The
   full lifecycle of any relayed task is reconstructable from the event stream -- this
   is the forensic non-repudiation the product thesis sells, now covering async calls.

4. **Governance binds at the proxy/store seam, never in a worker.** Ownership
   authorization, digest re-verification, and consent gating attach to
   `GovernedTaskStore` / the existing guards on the request path -- the same seam that
   governs synchronous `tools/call`. There is no background execution thread, so the
   "single bug means governance silently does not bind" failure mode ADR-008 warned
   about is structurally excluded, not merely tested against.

5. **Build the seam now; activate on first real upstream.** ADR-008 required **both**
   triggers before any build. This ADR relaxes that to: **build the relay seam now**
   (trigger (b) is met and the code largely exists dormant), and **activate relay for
   an upstream the first time it actually emits a task** (trigger (a), per-upstream).
   Until an upstream emits a task, the current clean `TaskRelayNotSupported` rejection
   remains the observed behavior -- so this ADR changes the *posture* and lands the
   *seam* without changing user-visible behavior on day one, and without the
   speculative-build risk ADR-008 named.

6. **Consent (`#322`) is the first activated beneficiary.** With the relay seam live,
   the built `TaskConsentGate` wires in: a relayed task entering `input_required` routes
   through the approval gate, the decision is recorded against `task_id`, and a task
   whose consent is absent is **failed fail-closed** (never left hanging). This ADR is
   the explicit unblocker named by `#322`.

**Carried forward from ADR-008 unchanged** (these were already the right calls):

- **Digest drift fails the task**, it does not merely refuse the result -- a task with a
  permanently-unavailable result is a zombie (ADR-008; `TaskDigestGuard`, `#320`).
- **Cancellation is best-effort relay** of `tasks/cancel`, no more responsibility.
- **An in-memory `task_id` mapping suffices** for a relay; a durable/distributed task
  store remains the executor's problem and stays out of scope.
- **Consent is decoupled** from the relay's existence: the relay works without it; the
  gate is an additive governance layer (Decision 6).

## Consequences

- **`#322` unblocks and lands right after the SDK v2 migration (`#547`).** The p1-high
  consent gate has been built and idle since `#302`; this decision is the only thing
  between it and activation.
- **The forensic moat extends to async.** Task governance was the one governed
  call-shape that was dormant; relay-with-governance makes the `task_id`-keyed event
  chain a real, queryable provenance record, consistent with the "govern the call path"
  positioning (ADR-009/repositioning).
- **No executor liabilities are taken on.** No scheduler, no result store, no GC/TTL
  correctness, no cancellation-race ownership, no worker/main-loop context bridge. The
  proxy stays a proxy.
- **"Do not advertise what does not run" still holds** (ADR-008 / ADR-009 Decision 6):
  the task capability is advertised in `capabilities.experimental` **only once the relay
  seam is live**, not on the strength of this decision alone.
- **Behavior is unchanged until an upstream emits a task.** Because activation is
  per-upstream on first real task (Decision 5), shipping the seam does not alter any
  current flow; the compatibility harness (`benchmarks#3`) continues to assert the
  clean `TaskRelayNotSupported` rejection until a tasking upstream exists, then flips to
  asserting a governed relay.

## Alternatives Considered

Each is an objection ADR-008 / PR `#368` raised; the decision above answers it.

- **Keep ADR-008 as written (relay-only, permanently; do not build).** Rejected: it
  strands a built, tested p1-high governance stack (`#319`/`#320`/`#321`/`#322`)
  indefinitely and leaves the one async call-shape ungoverned, now that the API it was
  waiting on (trigger (b)) has stabilized.
- **"Dead handle plus misleading error."** (`#368`'s motivating defect.) Answered by
  Decision 2: a relayed handle is recorded in `GovernedTaskStore` with a `TaskCreated`
  event at relay time, so a follow-up `tasks/get` always finds it -- the failure mode
  cannot recur, because we track instead of pass through.
- **"Speculative build -- a relay for upstreams that do not exist."** Answered by
  Decision 5: build the seam now (the code is mostly written and dormant), but activate
  per-upstream on first real task. No speculative *activation*.
- **"Experimental-API coupling / churn."** Answered by Context (1): trigger (b) is met;
  `mcp==2.0.0b2` makes Tasks a first-class negotiated extension. (Beta may still move to
  b3/rc; the seam targets the extension's stable shape, and the `#547` migration owns
  tracking that.)
- **"Species change / worker-thread -> main-loop context bridge."** Answered by
  Decision 4: governance binds at the proxy/store seam on the request path; there is no
  background execution thread, so the bridge does not exist to break.
- **"Consent has no serving path."** Answered by Decision 6 + the SDK v2 elicitation
  surface: the built `TaskConsentGate` gates `input_required` through the approval path;
  absent consent fails closed.
- **"Off-thesis -- Envoy does not run your cron jobs."** Answered by Decision 1: relay
  is not execution. Hangar governs the call path of a task an upstream owns; it never
  becomes the job runner.
- **Full executor (create/own/store tasks).** Rejected, same as ADR-008: it is a change
  of species with job-runner failure modes, off-thesis, and unnecessary for governing
  the call path.

## Activation

**Activated 2026-07-22** by maintainer decision, on SDK v2 (`mcp==2.0.0b2`), after
the relay seam shipped dark across four phases (`mcp-hangar#580`/`#581`/`#582`/`#583`,
consolidated onto the v2 integration branch by `#584`) and the consent gate wired in
(`#322`). Activation is the flip of the `relay_tasks_enabled` kill-switch to its new
default (`True`); the switch is retained for a fast, per-deployment rollback.

What activation does and does not change, against the decisions above:

- **Per D5 (build now, activate on first real upstream):** the flip makes the seam
  *live*, but the relay itself still only engages the first time an upstream actually
  emits a task. No synchronous `tools/call` flow changes on the flip; a deployment
  whose upstreams never emit tasks observes no behavioral difference.
- **Per D6 + "do not advertise what does not run" (ADR-009):** because the seam is now
  live, the `tasks` capability is advertised at `INITIALIZE`. This is the honest
  signal that governed relay is available — not a claim that a task is in flight.
- **Per D4 (governance binds at the seam, never in a worker):** unchanged and
  structural; activation adds no execution thread.
- **`benchmarks#3`** flips in lockstep: its governance-surface axis moves from
  asserting the `tasks` capability is *absent* (relay-only) to asserting it is
  *present*, matching the activated gateway.

The consent gate (`#322`) is live with the flip (D6): a relayed task entering
`input_required` is resolved through the synchronous elicitation approval path, and a
task whose consent is absent is failed fail-closed, never left hanging.

## References

- Supersedes (in part): [ADR-008](ADR-008-tasks-relay-only.md) (relay-only).
- Implementation of the prior decision: `mcp-hangar#368` (PR -- reject upstream task
  handles cleanly, `TaskRelayNotSupported`).
- Governance building blocks: `mcp-hangar#319` (ownership), `#320` (digest guard),
  `#321` (lifecycle audit events), `#322` (consent gate -- the named unblocker),
  parent epic `#302` (WS-4).
- Trigger (b) evidence: `mcp-hangar#547` (SDK v2 spike / breaking-change catalog;
  `mcp==2.0.0b2` promotes Tasks to a first-class extension). SEP-2663 (MCP Tasks).
- Compatibility assertion: `benchmarks#3` (the relay-only axis; flips to asserting the `tasks` capability is present on activation — 2026-07-22, see [Activation](#activation)).
- Foundations: ADR-002 (event sourcing -- the provenance chain), ADR-004 (digest pinning).
