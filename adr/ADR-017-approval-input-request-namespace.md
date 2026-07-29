# ADR-017: Pending Approvals Use `io.mcp-hangar/approval`, and Carry No Requested Schema

**Status:** Accepted
**Date:** 2026-07-29
**Authors:** MCP Hangar Team
**Related:** [ADR-016](ADR-016-approval-resolution-chokepoint.md) (one authorized chokepoint), [ADR-015](ADR-015-vendored-task-wire.md) (the SEP-2663 wire), core#662, [modelcontextprotocol#2919](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2919).

## Context

ADR-016 rebuilt approval *resolution*. This decides how a pending approval is *expressed*, which is the half that has to exist before the argument at modelcontextprotocol#2919 can be made honestly.

SEP-2663 pauses a task with an `inputRequests` map: server-assigned ids to descriptions of what is wanted. The descriptions are a closed union of three methods, and two of them are `@deprecated` in the same 2026-07-28 revision that introduced the map. What is left is `elicitation/create`.

`elicitation/create` asks the **connected client** for input. An approval gate exists because the connected client is not the party permitted to decide — that is the entire premise. So the one surviving method in the union cannot express the thing, and the gap is not incidental: the protocol models the easy half of a need whose hard half is *someone else must approve this*.

Hangar has lived with the consequence. The approvals layer resolves out of band, over a webhook and a REST endpoint, invisible to the MCP client: it observes a slow tool with nothing to display, cancel, or attribute.

## Decision

**1. A pending approval is a method-discriminated input request under `io.mcp-hangar/approval`.**

Reverse-DNS under a domain we control, matching the convention the protocol already uses for extension keys (`io.modelcontextprotocol/tasks`). The value is `method` plus `params`, which is the shape a method-carrying union takes.

The model is internal. Nothing is served under this identifier yet, and Hangar does not advertise it — per ADR-009, we do not advertise what does not run.

**2. It serializes to an `inputRequests` value with no transformation.**

That is the constraint the model is built against, and it is what makes this preparatory rather than speculative. If #2919 lands, `GovernedTaskStore` plugs in as its backend and the value we already produce goes on the wire untranslated. If it lands with a different identifier, we migrate an internal constant — the namespace is ours, the migration is entirely inside the process.

**3. It carries no `requestedSchema`, and that absence is the decision.**

Including one is the obvious move: an unaware client would then render *something*. It would render the wrong thing. A value with a schema looks like an elicitation, and an elicitation is answerable by the caller — reintroducing exactly the confusion the gate exists to prevent, at the one moment the system is asking a third party to decide.

A client that cannot recognise the method should be able to display that something is pending and have nothing to fill in. So `message` is present, for display, and no schema is. Anyone who answers regardless is answering a key with no schema, and resolution authorizes `approval:resolve` in the command handler either way (ADR-016). The wire discourages it; the chokepoint refuses it.

**4. The subject binds the call by hash; it does not carry the arguments.**

`argumentsHash`, plus the server and tool names. The subject travels to whoever is deciding, and the arguments may hold values that are not theirs to see — Hangar redacts on the audit path, not here. The hash still binds the decision to one exact invocation, so approving does not approve a different call to the same tool.

**5. It names a required permission, not an approver.**

`requiredPermission: "approval:resolve"`. Naming an individual would imply a routing guarantee this model does not make: it does not deliver, it describes. Delivery is an adapter's job (ADR-016, Decision 4).

## Consequences

The upstream argument becomes demonstrable rather than hypothetical. We can point at a working mechanism and say *this is the shape, and here is the field we cannot express in the union you have*.

Nothing about the current behaviour changes. Approvals still resolve out of band; the client still sees a slow tool. Folding this onto the governed-task path is WS-6 and stays gated on #2919 or on a deliberate decision to serve our own namespace without upstream blessing.

If #2919 is rejected outright, the model still earned its place — it replaced an untyped aggregate with one that states who may decide, about what, until when, and on what basis, which was worth having regardless of the wire.

**A cost worth naming:** publishing an identifier, even internally, makes it quotable. If the eventual protocol shape differs, someone will have built against `io.mcp-hangar/approval` in the interim. That risk is accepted and bounded — the namespace is ours, so a migration is ours to make, and nothing is advertised today.

## Alternatives Considered

**Reuse `elicitation/create` and encode the approval semantics in the message.** No new namespace, works with clients today. It also tells the caller "answer this", which is false and dangerous: the caller is the party being gated. Rejected on the same ground as Decision 3.

**Wait for #2919 before modelling anything.** Avoids the quotable-identifier cost. It also means arriving at the discussion with a request rather than an implementation, which is the weaker position — and leaves our own pending approvals untyped in the meantime, which was itself a real gap.

**Use a bare name like `approval` instead of reverse-DNS.** Shorter, and collides with anyone else's `approval` the moment two extensions meet. The protocol chose reverse-DNS for extension keys for this reason.

**Include a schema but mark it read-only.** There is no such marker in the union, and a convention we invent is one a client is free to ignore. An absent schema cannot be ignored.

## References

- core#662 — the model and its tests
- [ADR-016](ADR-016-approval-resolution-chokepoint.md) — the authorization chokepoint this relies on
- [ADR-015](ADR-015-vendored-task-wire.md) — why the SEP-2663 wire is vendored
- [ADR-009](ADR-009-independent-release-topology.md) — do not advertise what does not run
- [modelcontextprotocol#2919](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2919)
