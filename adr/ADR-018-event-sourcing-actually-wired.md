# ADR-018: Event Sourcing, Actually Wired -- and What Is Not Event-Sourced

**Status:** Accepted
**Date:** 2026-08-05
**Authors:** MCP Hangar Team
**Supersedes:** [ADR-002](ADR-002-event-sourcing.md) (Event Sourcing)
**Related:** [ADR-001](ADR-001-cqrs.md) (CQRS), [ADR-014](ADR-014-tasks-relay-with-governance.md) (task provenance rests on this), core#753.

## Context

ADR-002 was accepted on 2026-04-17 and never came true. That is not a criticism of the decision; it is a statement about the wiring, and it went unnoticed for the ordinary reason: every part of the mechanism existed, so every review of every part passed.

The audit in core#753 has the evidence. In short: the only methods that wrote to the event store had no production caller, `data/events.db` had held zero rows since it was created, the aggregate ADR-002 named had been deleted as never wired, and aggregates were in fact persisted as state snapshots by `SQLiteMcpServerConfigRepository` -- the mechanism ADR-002 said it was replacing.

Meanwhile the claim had escaped into places harder to correct than code: the website advertised an "append-only, event-sourced chain", the README advertised "an event-sourced trail", and ADR-014 built task provenance on top of it. A user could reasonably have relied on that for compliance evidence.

Two honest options existed: retire the ambition, or finish it. This ADR finishes it, and records the finished shape rather than the intended one -- several decisions below are not what the first draft of this document proposed, because building them changed the answer.

## Decision

### 1. An event that names an aggregate is that aggregate's history, and is persisted by construction

The stream is derived from the event, not chosen by the caller. `EventBus.publish` resolves the stream from the event's own identity (`mcp_server_id`, `group_id`, and the `mcp_server_name` that discovery reports before an id exists) and appends before delivering.

This replaces a two-method design -- `publish` for delivery, `publish_to_stream` for delivery plus persistence -- under which 34 call sites used the forgetful one against 10 that did not. Registering a server, the most audit-relevant act this system performs, went through `publish` and was never written down: an aggregate's stream began with its first *edit*. "Which method should I call" is not a question callers answer reliably, and answering it wrong was silent.

An event naming no aggregate -- an authentication, a batch outcome -- is delivered and not stored. There is no history for it to be part of, and inventing a bucket to hold it would make the log harder to read rather than more complete.

### 2. The stream is the source of truth for persisted state, and only for persisted state

**Replayed:** lifecycle state, health counters, invocation totals, last use. A server that was `DEGRADED` before a restart comes back `DEGRADED` -- discarding that would let any process restart clear a circuit breaker, and an enforcement plane must not hand out that reset quietly.

**Not replayed, because configuration answers them:** mode, command, image, endpoint, env, TTLs, thresholds. *What should this be* is not a question history answers, and the configuration repository remains their home.

**Never restored:** the live transport client and any process handle. Liveness is re-earned by connecting, never assumed from a record -- so a restored aggregate keeps its counters **and** still has to reconnect before it can serve. That combination is the point: fail-closed on the record, re-probe for the truth.

This split is the hardest part of the work and it is where a naive "event-source everything" fails.

### 3. Delivery is at-least-once, via a checkpoint over the log rather than a separate outbox

The order is append, deliver, then advance a durable high-water mark. A crash between the append and the mark re-delivers on the next startup sweep instead of losing the events; a crash before the append loses nothing, because nothing was claimed. Handlers must therefore be idempotent, keyed on `event_id`.

The draft of this ADR called for an outbox table. The log already is one: it is append-only, ordered by `global_position`, and durable. A second table holding the same rows would have added a moving part, a second thing to keep consistent with the first, and no guarantee the first cannot give. The checkpoint is a row.

The previous behaviour -- append, then publish in a loop, with no retry and no mark -- is at-most-once, and is not adequate for a chain described as an audit trail.

### 4. One event-store hierarchy

`domain/contracts/event_store.py` is the port; `infrastructure/persistence/` holds the adapters. The parallel hierarchy -- its own `EventStore` ABC, a second `ConcurrencyError`, a second `InMemoryEventStore`, a `FileEventStore` and a global singleton that handed two production components a store nothing wrote to -- is deleted.

### 5. What is deliberately absent from the log is declared, with its reason

An empty log and a log that deliberately omits something look identical in a code review a year later. Two lists in `pyproject.toml` carry the difference: events reserved for a consumer that exists with no producer yet, and events with neither. Both may shrink; neither may grow without a stated reason. A build fails on an undeclared addition.

The rule that decides membership is that an event log earns its keep by holding what happened *once*. A discovery cycle completing is not that: at the default 30s refresh it is 2880 rows a day per gateway saying nothing changed. Source health is a gauge that already exists. Both are declared out, in writing, next to the reason.

### 6. CQRS at the edge is out of scope here

Most REST routes still call services directly, and routing every mutation through the command bus is a separate decision and a separate ADR; conflating it with this remodel would make both harder to review and to revert.

One exception was made and is worth naming: discovery now registers through `CreateMcpServerCommand` rather than building the aggregate itself. That was not tidiness -- the direct path bypassed the duplicate guard, the SSRF check and the registration event, so a discovery source could add an unvalidated server with no record that it happened.

## Implementation notes

- Stream ids come from one helper in the shared kernel. The mismatch this closed -- writers producing `mcp_server:{id}` while the history query read `mcp_server-{id}` -- was invisible precisely because no writer ever ran.
- Snapshots remain a performance device inside the store's read path, never a source of truth.
- Events are compared on payload, not identity, and nothing mutates an event in flight. That invariant is tested rather than enforced by `frozen=True`: freezing the base class freezes all 85 subclasses and breaks any downstream that subclasses one, which is a wide breaking change against a mutation that does not currently happen.
- Migration: existing configuration state is not backfilled into per-aggregate history. Replay before a stream's first row is not claimed and must not be advertised.

## Consequences

**Good.** The audit claim is true: creating a server, discovering one, refusing one and losing one are all in the log, each carrying the provenance of the door it came through -- `api`, `cli`, `discovery:kubernetes`. The health endpoint's `durable=True` is a statement about a file that is written to.

**Costs.** Every handler must be idempotent. Replay cost grows with stream length. Schema evolution stops being free: an event's shape becomes a compatibility surface, which is what the upcaster chain is for. Persistence is now on the publish path, so a store that cannot write is a hot-path failure -- handled by delivering anyway and logging loudly, because losing enforcement and metrics handlers to a disk problem is the worse outcome.

**Accepted limits, stated rather than discovered.**

- No cross-aggregate transactions, and no global ordering -- only per-stream.
- Replay reconstructs persisted state, never runtime state, per decision 2.
- **Rehydration is implemented for `McpServer` only.** Groups, approvals and tasks record their history but are not rebuilt from it; their state still comes from their repositories on startup. The log is complete for them, the replay is not, and that gap is a known one rather than an assumed capability.
- The durability of the delivery mark matches the store it belongs to. An in-memory store gets an in-memory mark: a configuration that cannot survive a restart does not get a promise that it will.
