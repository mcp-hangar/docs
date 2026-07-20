# ADR-008: Task Governance is Relay-Only -- Hangar is a Task Relay, Not a Task Executor

**Status:** Accepted -- partially superseded by [ADR-014](ADR-014-tasks-relay-with-governance.md) (the "relay-only *permanently*" and "do not build the relay yet" decisions are lifted; other decisions carried forward)
**Date:** 2026-07-02
**Authors:** MCP Hangar Team

## Context

The MCP Tasks extension (SEP-2663) lets a `tools/call` return a task handle
(`CreateTaskResult`) that the client then drives via `tasks/get` / `tasks/update`
/ `tasks/cancel`. Hangar has built and unit-tested full per-task governance --
ownership authorization and digest re-verification, both fail-closed, wired
through `GovernedTaskStore` and `enable_tasks(...)`. That governance is currently
**dormant**: Hangar never emits a task handle, and no MCP server in the registry
returns one either.

Hangar's product thesis is *govern the call path* -- it is a proxy, not a job
runner. The question "should Hangar emit task handles" reduces to two forks:
**relay vs executor**, and **now vs later**. A relay tracks and governs tasks that
an upstream creates. An executor decides to convert calls into tasks and owns the
background work itself.

One concrete defect exists today: an upstream task result passes through the proxy
untouched, the client receives the handle, then `tasks/get` finds no local task and
returns "Task not found". That is fail-closed *by accident* -- a dead handle with a
misleading error, the async form of "an advertised capability that never runs".

## Decision

1. **Hangar is a relay, not an executor -- permanently.** The executor role
   (Hangar deciding to make tasks and owning background lifecycle, result storage,
   TTL/GC, cancellation correctness, and the worker-thread to main-loop context
   bridge where a single bug means governance silently does not bind) is a change
   of *species*, not a role expansion. Envoy does not run your cron jobs. This
   closes the "convert long-running calls" / "per-tool" / executor variants.

2. **Client-task-augmented calls are not a separate model.** A `tools/call`
   carrying a `task` parameter is forwarded upstream; the upstream decides whether
   to emit a handle; Hangar governs what returns. That collapses into the relay.

3. **Do not build the relay yet.** No registry upstream emits `CreateTaskResult`,
   and the extension ships with the 2026-07-28 RC. Building a relay for upstreams
   that do not exist is the executor's speculative trap at smaller scale.

4. **Interim (do now): reject upstream task handles explicitly.** Detect an
   upstream task result in the proxy path and return a clear error
   (`TaskRelayNotSupported`) instead of a dead handle -- deliberate fail-closed,
   not accidental.

5. **Trigger to build the relay -- both conditions, not either:** (a) a real
   upstream emitting tasks in production use, **and** (b) the mcp task API
   graduates out of `mcp.server.experimental`.

## Consequences

- The built governance (`GovernedTaskStore`, ownership `#319`, digest `#320`, and
  the consent primitive `#322`) stays **dormant until the relay is built**. This
  must be stated plainly in the docs -- built, tested, asleep -- before anyone
  infers it is active.
- Decisions pre-committed for when the relay is built:
  - **Digest drift:** re-verifying the tool digest at `get_result` is correct (that
    is the moment trust is delivered); on drift, **fail the task**, do not merely
    refuse the result -- a task whose result is permanently unavailable is a zombie.
  - **Cancellation:** the relay proxies `tasks/cancel` best-effort, exactly as the
    spec promises -- no more responsibility than that.
  - **Consent is decoupled:** a task entering `input_required` with no elicitation
    subsystem is failed fail-closed by the relay; consent (`#322`, needs an
    elicitation relay) does not gate the relay and lands separately if ever.
  - **Mapping:** an in-memory `taskId` mapping suffices for a relay; a durable or
    distributed task store is the executor's problem, which this ADR rejects.
- When both trigger conditions hold, the relay is weeks, not quarters: a `taskId`
  mapping plus relaying `tasks/get` / `tasks/cancel` with the existing fail-closed
  authorization, on top of the store already built.

## Alternatives Considered

- **Executor (Hangar converts calls to tasks / owns async execution).** Rejected:
  it makes Hangar a job runner with new failure modes (leaked background work,
  result-store growth, cancellation correctness, the silent context-bridge bug),
  off the "govern the call path" thesis, and coupled deeply to an experimental API.
- **Do nothing.** Rejected as incomplete: the accidental dead-handle needs the
  explicit rejection (decision 4). Waiting on the *relay* is correct; waiting on
  the *posture fix* is not.

## References

- SEP-2663 (Tasks extension); `mcp.server.experimental` (task support, 1.26.0).
- `src/mcp_hangar/application/tasks/governed_task_store.py`; task primitives
  `task_ownership.py` / `task_digest_guard.py` / `task_consent.py`.
- Issues: `#302` (WS-4 epic, full status), `#319` / `#320` (shipped, dormant),
  `#322` (consent, deferred).
