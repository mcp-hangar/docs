# ADR-019: One Storage Decision, and Two Backends That Are Never Mixed

**Status:** Accepted
**Date:** 2026-08-06
**Authors:** MCP Hangar Team
**Related:** [ADR-018](ADR-018-event-sourcing-actually-wired.md) (what the event log is), [ADR-001](ADR-001-cqrs.md) (CQRS), core#779, core#778 (the HA readiness audit this unblocks).

## Context

Storage was decided in two independent places. `auth.storage.driver` chose where API keys and role assignments lived; `event_store.driver` chose where the event log lived. Nothing compared them, so a deployment could keep its credentials in PostgreSQL and its audit trail in a local SQLite file and look correctly configured from either end.

That was not a hypothetical risk. The PostgreSQL path covered API keys and roles and assigned `None` for the tool-access policy store. Two consumers were gated on that value: the query handler that manages policies, and the startup replay that loads persisted policies into the runtime resolver. Selecting PostgreSQL therefore switched off the layer that decides which tools a principal may call -- including what sits behind `approval_list` -- with no error and no warning. A partial backend was expressible, so one shipped.

The immediate trigger was high availability. A gateway that runs on more than one node needs storage more than one process can share, and SQLite is a file. The hardening cookbook already recommended `postgresql` "for HA (all replicas share it)" while the extra installed `asyncpg` and the code imported `psycopg2`, so the recommended path could not start. Answering the HA question required answering the storage question first.

## Decision

### 1. `persistence.backend` is the storage decision, and it names a bundle

```yaml
persistence:
  backend: postgresql
  postgresql:
    host: db.internal.example
    database: mcp_hangar
```

One name selects every concern the gateway persists: the event log and its delivery mark, server configuration, the audit trail, saga state, approvals, API keys, roles, tool-access policies and metric history. The block under the backend's own name is handed to its factory untouched, so `data_dir` means nothing to PostgreSQL and `host` means nothing to SQLite, and neither has to know the other's vocabulary.

### 2. A backend serves every concern or it is refused

Selection verifies that all ten are provided and raises with the missing ones named -- all of them at once, because an operator fixing one restart at a time is its own failure mode. Returning `None` for a concern is not available.

This is the rule the `tap_store = None` defect could not have survived. It makes "either one or the other" enforceable rather than conventional: a backend cannot be half-registered.

### 3. Two separate implementations, neither privileged

`sqlite` is the standalone answer -- files under one directory, nothing to install, nothing to run, and not shareable between processes. `postgresql` is the multi-node answer and the only one two gateways can share.

They are peers. Both are registered factories, both are checked by the same rule, and each owns its own driver and its own SQL: `sqlite3` is known to one package, `psycopg2` to the other through the shared connection factory, and **no adapter anywhere carries a dialect branch**. That is the property that makes these two implementations rather than one implementation with two modes -- and the property that makes a third backend a package plus an entry point under `mcp_hangar.persistence_backends`, exactly as a discovery source has been since the registry in core#766.

### 4. A contradiction is refused, not resolved

Selecting a backend while a legacy per-subsystem key names a different one fails at startup. Every precedence rule silently ignores half of what the operator wrote, and the half that loses is the one they wrote most recently and are most sure about.

`memory` is exempt: it is a testing choice rather than a storage backend, so it never conflicts.

### 5. Omitting the block changes nothing

Without `persistence.backend`, every subsystem configures its own storage exactly as before. 2.4.0 is released; a storage rewiring must not change what a working configuration does.

## Consequences

**Good.** A multi-node deployment has a storage answer that is complete rather than partial, and the completeness rule means the next concern added to the gateway cannot quietly go missing from one backend. Two concerns that had no port at all -- saga state and metric history -- have one, which is why they could not be served from a second backend before.

**Costs.** Ten adapters exist twice, and a change to a persisted shape is now two changes. That is the honest price of two implementations, and it is preferable to one implementation that branches: a dialect branch inside a store is a place where the two backends can differ without anyone noticing, and a second file is not.

**Accepted limits, stated rather than discovered.**

- **Storage is necessary, not sufficient, for HA.** Approval holds, session suspension, rate limits and the discovery loops remain process-local, so more than one replica is still wrong until coordination is addressed (core#778). This is what coordination will store its leases in.
- Consumers are being moved onto the selected backend in sequence. The event log and its delivery mark take theirs from it; the rest still build their own when no backend is selected, which is the compatibility path rather than the destination.
- No migration is provided between backends. Selecting PostgreSQL on a gateway that has been running on SQLite starts an empty database; moving existing history is a separate problem and is not claimed.
