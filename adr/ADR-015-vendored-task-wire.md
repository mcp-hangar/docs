# ADR-015: The Tasks Wire is Vendored -- `mcp_types.Task*` is a Fossil, Not a Moving Target

**Status:** Accepted
**Date:** 2026-07-28
**Authors:** MCP Hangar Team
**Supersedes:** [ADR-014](ADR-014-tasks-relay-with-governance.md) in part -- corrects the factual premise of its Context ("trigger (b) is met"). Every decision ADR-014 makes about *governance* stands unchanged; only the claim about which wire the SDK provides is wrong.
**Related:** [ADR-008](ADR-008-tasks-relay-only.md) (relay-only), [ADR-009](ADR-009-independent-release-topology.md) ("do not advertise what does not run"), core#322, core#632, core#634, python-sdk#3005.

## Context

ADR-014 activated the governed task relay on a stated trigger: SDK v2 "promotes Tasks out of `experimental` into a first-class, negotiated protocol extension", so "the API ADR-008 called too churny to build against is now stable and discoverable."

The first half is true. The second half is not, and the difference shipped.

What SDK v2 exposes in `mcp_types` is the **SEP-1686** generation of Tasks -- the design that the 2026-07-28 revision *removed from the core spec*. `mcp_types`' own module comment says so: Tasks are "introduced in 2025-11-25, removed from the core spec in 2026-07-28 (continuing as an extension). Defined here types-only; their methods are not in the request/notification unions." Those types are kept so a server can still speak 2025-11-25. They are not the extension.

The replacement, SEP-2663, is wire-incompatible with them on nearly every field:

| | `mcp_types` (SEP-1686) | SEP-2663 |
|---|---|---|
| create result | nested `{task: {...}}` | flat, `resultType: "task"` |
| TTL | `ttl` (required) | `ttlMs` (required, nullable) |
| poll hint | `pollInterval` | `pollIntervalMs` |
| `tasks/get` → | flat snapshot | snapshot with outcome inlined |
| `tasks/result` | present | **removed** (`-32601`) |
| `tasks/list` | present | **removed** |
| `tasks/update` | absent | **required** |
| `resultType` | absent entirely | required on every result |

### How the wrong premise survived review

It was hedged, not assumed. `_sdk_compat` carried capability probes -- `HAS_LIST_TASKS`, `HAS_TASKS_UPDATE` -- so that "the `tasks/list` advertise + serving drop themselves when the SDK removes the type, and the `tasks/update` handler + answer path light up when the SDK adds it." A version-independent feature probe is normally the *right* instinct, and it is why nobody re-checked.

It cannot work here. The probes watch a module that is finished. Measured across two releases thirteen days apart -- `mcp==2.0.0b2` (14 Jul) and `2.0.0rc1` (27 Jul) -- the surface is byte-identical: `ListTasksResult` still present, `UpdateTaskRequest` still absent. python-sdk#3005 states the reason in its own design: the extension defines its **own** SEP-2663 models *because* they are wire-incompatible with what stayed in `mcp_types`. Nothing will ever be added to or removed from the fossil, so the probes were latches that could never trip.

### What it cost

`2.0.0rc2` was cut to undo it. `relay_tasks_enabled` defaulted to True, so `2.0.0rc1` advertised a `tasks` capability at INITIALIZE and then served SEP-1686 shapes. A client that negotiated 2026-07-28 was told the server speaks Tasks and handed a reply it cannot parse -- with no way to detect the mismatch first, because the capability *is* the advertisement. That violates ADR-009's rule in the one direction that reaches users: **do not advertise what does not run.**

Exposure was small but not accidental: `pip` will not select a pre-release unaided, but the v2-preview documentation instructs readers to run `pip install --pre mcp-hangar`.

## Decision

1. **The Tasks wire is vendored in `mcp_hangar/tasks_wire.py`.** Request params, results and the served method set are defined by Hangar, not imported from the SDK.

2. **`mcp_types.Task*` must never appear in a serving path.** Not as a base class, not as a constructor, not as a validation target. Enforced by a test that parses `tasks_wire.py`'s AST and fails on any `mcp_types` import -- source text is not enough, since the module's own docstring names `mcp_types` throughout to explain the prohibition.

3. **Vendored means tracking SEP-2663 and python-sdk#3005, not inventing a dialect.** Field names, defaults and nullability follow #3005 so that when it merges, `GovernedTaskStore` attaches as its backend and `tasks_wire.py` retires instead of forking. A third dialect would be a worse outcome than the fossil.

4. **Divergences from #3005 require a stated reason in the module docstring.** Exactly one exists today: `GetTaskResult` declares `inputRequests`. #3005's does not -- its `GetTaskResult(Task)` has no such field and inherits pydantic `extra="ignore"`, so a server's map is dropped on parse, breaking the in-task input loop the same PR documents. Hangar's mid-flight consent gate reads that map, so dropping it would break consent.

5. **Capability advertisement is gated on the served wire, never on SDK symbol presence.** `relay_tasks_enabled` stays default-False until the SEP-2663 shapes are actually served. Symbol probes may still gate *optional* behaviour; they may not gate what is advertised.

## Consequences

**Wanted.** The served wire stops depending on a module that will not change. The advertisement becomes truthful. Divergences from the ecosystem become deliberate and documented rather than emergent. `-32021` / `-32601` / `-32602` error semantics can be implemented to spec, none of which the fossil expresses.

**Accepted cost.** Hangar now maintains protocol models it does not own, and they can drift from SEP-2663 as the SEP moves. The mitigation is the retirement path in Decision 3, not vigilance -- vendoring is a bridge with a defined end, and #3005 merging is the end.

**A rule that generalises past Tasks.** A capability probe is only a hedge when the thing probed is still moving. Against a frozen module it silently encodes the current answer as permanent. Before relying on one, establish that the watched symbol *can* change -- upstream's own design intent, not just its current contents. Here upstream had already published that intent in an open PR; nobody read it, because the probe felt like it made reading unnecessary.

**Not reopened.** Hangar still does not execute tasks. ADR-014's governance model -- ownership binding, digest re-verification, fail-closed consent, upstream truth -- is untouched; it was always independent of which wire carried it, which is why the fix was a wire change and not a redesign.

## Alternatives Considered

**Wait for python-sdk#3005 to merge, keep the relay dark.** Rejected. The PR is open with conflicts and a week of no movement; its merge is not ours to schedule. It would also leave `2.0.0rc1`'s bad advertisement live in the meantime, which is the acute problem.

**Serve the SEP-1686 wire and advertise 2025-11-25 only.** Rejected. It is coherent, and it forfeits the reason the v2 line exists: Hangar's whole position is being current with the modern surface. It would also strand the mid-flight consent work against a generation whose Tasks feature is removed.

**Keep using `mcp_types` and translate at the edge.** Rejected as the worst of both. Translation still requires knowing the target shapes -- the vendored models -- while adding a lossy hop through types that cannot express `resultType`, `tasks/update` or a nullable `ttlMs`. Fields with no fossil equivalent would have to be smuggled through `_meta`.

**Fix the probes to watch the extension package instead.** Deferred, not rejected. Once #3005 merges its models become the thing to track, and a probe against *them* is sound because they are the live surface. That is Decision 3's retirement path.

## References

- SEP-2663 -- Tasks as a negotiated extension (`io.modelcontextprotocol/tasks`)
- SEP-2243 -- `Mcp-Method` / `Mcp-Name` stateless routing; SEP-2663 mandates `Mcp-Name: <taskId>` on `tasks/*`
- [python-sdk#3005](https://github.com/modelcontextprotocol/python-sdk/pull/3005) -- reference implementation the vendored models track
- core#632 -- default the relay off; core#634 -- vendor the wire; core#322 -- mid-flight consent
- [ADR-014](ADR-014-tasks-relay-with-governance.md) -- the governance model this corrects the wire premise of
