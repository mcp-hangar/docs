# ADR-020: More Than One Gateway -- What Is Shared, What Is Leased, and What Stays Local

**Status:** Accepted
**Date:** 2026-08-06
**Authors:** MCP Hangar Team
**Related:** [ADR-018](ADR-018-event-sourcing-actually-wired.md) (the log this rests on), [ADR-019](ADR-019-one-storage-decision-two-backends.md) (the storage decision this needed first), [ADR-001](ADR-001-cqrs.md) (CQRS), core#778 (the readiness audit), core#788 (the flow analysis), core#789 (the design), core#790 (the work).

## Context

The gateway was written as one process. Nothing said so -- the deployment guide showed a Kubernetes `Deployment`, the hardening cookbook recommended PostgreSQL "for HA (all replicas share it)", and the operator's CRD had a replica count. What made it one process was not a decision but an accumulation: state kept in dictionaries, loops that converge the fleet running unconditionally, a suspension registry that was a set, and a lease on nothing.

The readiness audit (core#778) found the shape of it. Running two replicas did not fail; it produced a system that disagreed with itself and reported success at every step. A server registered on one was invisible to the others. A session suspended by a detection rule was refused by one replica and served by the rest, so retrying the request walked past the block. Discovery ran everywhere at once, so a server registered by one replica could be deregistered by another in the same second, forever.

Two honest options existed: document one instance as the only supported topology, or make more than one work. This ADR records the second, as built.

**A prerequisite came first and has its own record.** Storage was decided in two independent places and a partial backend was expressible; ADR-019 made it one decision with two complete implementations. Nothing here is possible without a store several processes can share.

## Decision

### 1. Every event carries the instance that produced it

`DomainEvent` gained `produced_by`. With one replica that is an audit convenience; with three it is the difference between a follower that can read the shared log and one that cannot, because a replica publishes locally *and* appends to the log it later tails, and without a producer on the row it cannot tell its own append from a peer's.

**The identity is minted, not configured.** A label -- the pod name, via the downward API -- prefixes it; a per-process suffix is always appended. Configuration that names the identity directly has one bad outcome nothing catches: three replicas rolled from one ConfigMap share an id, each treats its peers' events as its own, and the tail goes silent while every health check stays green.

A row written before the field existed reads as `UNKNOWN_PRODUCER`, never as the reader. The reverse would have a tailer drop history as its own work.

### 2. The log is followed with a cursor the store defines, not a position

`global_position` is a `BIGSERIAL`, and allocation order is not commit order. Two appenders can be handed 5 and 6; the holder of 6 can commit first; a cursor past 6 never sees 5 arrive. Measured against PostgreSQL 16: the event at 5 is not delivered late, it is **never delivered**.

So `read_since` takes an opaque cursor. SQLite resumes from a position, because one writer makes allocation order commit order -- the same property that makes it the standalone backend. PostgreSQL resumes from a transaction watermark (`pg_snapshot_xmin`), which cannot pass a transaction still in flight. The trade is stated rather than discovered: an append that holds its transaction open holds the tail back for every replica. It lags; it does not skip.

**The obvious alternative was measured and rejected.** Allocating positions from a counter row inside the append transaction puts a row lock on the path of every tool invocation, since `ToolInvocationCompleted` is appended per call. At sixteen concurrent writers it delivers ~1400 appends/s against ~6600 for the sequence, with p99 latency ten times worse. The `xid8` column that replaces it costs nothing measurable.

### 3. Management is leased; serving is not

Discovery, garbage collection, TTL deregistration and the metric snapshot worker are convergence loops. Three of them against one database is three sources of truth arguing. They run only while this instance holds a lease -- a row with a TTL and a **generation**, in the storage backend the deployment already chose.

Deliberately not the Kubernetes `Lease`: core runs on compose, on podman and from a `pip install`, and a coordination primitive that only exists inside a cluster would make those deployments second-class. Deliberately not called *failover*: `McpServerFailoverSaga` already means moving traffic off an unhealthy upstream.

**The generation is what makes a leader safe.** A TTL alone does not: a holder that stalls past its expiry has no way to know time has passed, and wakes to finish a sweep that undoes its successor's work. Carried into the `WHERE` clause of a destructive write, a stale generation matches zero rows.

The gate is asked **per cycle**, not once at startup, and the keeper gives the lease up on its own if it has not managed a successful renewal within a deadline shorter than the TTL -- because an unreachable database is not an answer, and the tenure is expiring on its clock regardless. It gives up slightly early rather than slightly late.

### 4. A handler declares whether it is a projection or an effect

Required at subscription, with no default: an unclassified effect exports the same tool call from three replicas, an unclassified projection leaves two of them stale, and both wrong answers are silent.

- A **projection** keeps a local view -- the tool catalogue, fleet membership, risk scores, the websocket feed. It runs on every replica for every event, whoever produced it, and publishes nothing.
- An **effect** acts outward -- SIEM export, cost accounting, alerts, enforcement. It runs **only on the instance that produced the event**.

That last rule is what makes exactly-once free: a tool call happens on exactly one replica, so the replica that did the work is the one that exports it. No cursor, no coordination, no leader bottleneck.

The classification landed *before* the tailer, not after. The tailer is what creates the duplicate-effect problem; it does not solve it.

### 5. What crosses the replica boundary, and what does not

The rule, applied four times and stated once: **state about this replica's own resources stays local; state about the fleet is shared.**

| | | |
|---|---|---|
| Fleet membership | shared | a projection; otherwise which servers exist depends on which replica you asked |
| Session suspension | shared | a decision about the *session*; local, it is a block avoided by retrying |
| Lifecycle state | local | answers "can *I* serve this"; in subprocess mode each replica runs its own child |
| Circuit breakers | local | shared, one replica with a network problem cuts a healthy upstream off from the rest |
| Rate limits | local | per instance, and said so; see the failure modes below |

### 6. Local modes belong to the instance that runs them

`subprocess` and `docker` do not describe a server the gateway talks to. They describe one it *runs* -- `docker run --rm -i`, stdio attached, held as a pipe inside one process. There is no address a peer could use, so a replica serving a call to such a server does not reach the existing copy; it starts its own, with its own mounted volumes.

They are refused at registration in a coordinated deployment, and refused again at launch on a follower. **The supported multi-replica configuration is `remote`-mode servers.**

Routing a follower's call to the holder was considered and rejected for now: it needs a peer-to-peer channel that does not exist, plus presence discovery, authentication between replicas and budgets across two hops. Sharding local servers across replicas is explicitly out of scope (core#788, core#789).

### 7. A cluster requires PostgreSQL, and is refused without it

Several replicas on a file-backed backend do not collide. Each gets its own file, grants itself its own lease -- the SQLite adapter always grants, correctly, because a file admits one writer -- runs its own management loops and holds its own fleet. They never disagree, because they cannot see each other, so every health check stays green while the deployment has as many fleets as it has pods. Measured: three replicas, all three reporting `manages_fleet: true`.

A `coordination:` block is the statement that these replicas are meant to be **one** gateway, and it is refused on storage they cannot share. The question is asked on the axis the operator controls rather than by inspecting the environment: a thousand pods each with their own storage are a thousand gateways, which is a legitimate thing to run. What is not legitimate is calling them one.

A backend that cannot be shared gets no lease keeper at all -- it would grant itself the lease every time, which is not coordination -- and `GET /api/system` reports `storage_is_shareable` next to a `coordinates_with_peers` that is true only when it is.

### 8. With a shared database, two versions coexist during every rollout

This is the standing rule, and it outlives every decision above. A rolling update runs the old and new images against one database, for as long as the rollout takes. **A schema change must therefore be compatible with the previous release**, in both directions, for at least one version:

- New columns are added nullable, or with a non-volatile default. The `xid8` column added in this work is nullable precisely so that adding it does not rewrite the events table under an exclusive lock. Verified with both versions running against one database: the older gateway, which does not know the column exists, appended a row and the column's default filled it in.
- **A new replica may see events whose records the old one did not write.** The two halves of a change do not arrive together during a rollout: an older gateway that registers a server emits the event but not the configuration row a newer one reads to rebuild it. The newer replica must decline rather than invent -- observed as `fleet_projection_no_record` in exactly this arrangement, which is a defensive branch that a rollout turns into an ordinary one.
- An event gains fields; it does not lose them or change their meaning. Events are persisted, so an old row must still deserialize -- the upcaster chain from ADR-018 is the mechanism, and absence is a signal in its own right.
- A row written by the new version must be readable by the old one, for the length of one release cycle.

## Consequences

**Good.** Three replicas serve one fleet, share one view of it, export one copy of each audit record, and converge it from exactly one place. A replica can be killed without the fleet forgetting anything, and the one that replaces it inherits the record rather than an empty dictionary.

**The window with no leader.** When the holder dies without releasing the lease, nothing manages the fleet until the TTL expires and a peer acquires it -- fifteen seconds by default. **Serving continues throughout**; what pauses is discovery, garbage collection, TTL deregistration and metric snapshots. A graceful shutdown releases the lease and reduces this to the time of one acquisition round.

**Failure modes, and what each one costs.**

| What happens | What breaks | What does not |
|---|---|---|
| The holder is killed | management pauses for up to the TTL | serving, on every replica |
| A holder stalls past its expiry | nothing: its destructive writes match zero rows | the new holder's work |
| The database is unreachable | management stops after the renew deadline; the tail stalls | serving from each replica's current view |
| A replica joins mid-life | it reads the fleet snapshot and tails from the head | it does not replay the cluster's history |
| A replica dies between appending an event and exporting it | that one outbound export | the event, which is in the log |
| Two replicas answer `manages_fleet: false` and none `true` | nothing is converging the fleet | serving; and `GET /api/system` says so |

**Rate limits multiply by the replica count.** The limiter counts per process, so a configured 10 rps admits 30 across three replicas. Dividing by the count drifts exactly when it matters -- a rollout runs N+1 replicas, a failure runs N-1 -- and a shared bucket puts a database round trip on the path of every call. The scope is stated in configuration and reported by `GET /api/system`; a fleet-wide limit belongs at the ingress, where the fleet has one entrance.

**What fencing covers, and what rests on local belief.** At the database there is never more than one holder: acquisition is a single conditional statement, and sixteen threads racing produce one winner. In *belief* there can be two, briefly -- an instance that stalls past its expiry believes it holds the lease until its keeper's next tick. Measured with `SIGSTOP`: the belief ended in the same second as the thaw, because the keeper's wait had already elapsed, but that is a scheduling accident and not a guarantee. What bounds the damage is fencing, and it does not cover everything:

| a stalled leader's action | what stops it |
|---|---|
| deregistering a server | the generation, in the `WHERE` clause -- zero rows |
| writing the shared circuit-breaker row | the lease gate |
| registering from discovery | local belief only |
| taking a metric snapshot | local belief only |
| starting a local-mode server | local belief only |
| health decisions | local belief only |

Deregistration is fenced first because it is the irreversible one: a re-registration is an upsert, a duplicate snapshot is one row too many, and a repeated discovery cycle is a wasted second.

**One logical PostgreSQL is assumed.** Everything above rests on the lease row being a single authority. A database that fails over to a stale replica could take the row back in time, and two instances would then both see a free lease. Nothing here detects that, and nothing here can.

**Two databases are indistinguishable from one, from inside.** Pointing two groups of replicas at different databases produces two fleets, each internally consistent, each reporting health. That is a configuration error nothing catches.

**Accepted limits, stated rather than discovered.**

- The propagation window for anything that travels by the log is one tail interval. For a session suspension that means a few seconds during which the block holds on the deciding replica and not yet on its peers.
- A replica that joins *after* a suspension does not inherit it: its cursor starts at the head, and session state is not part of the fleet snapshot.
- `subprocess` and `docker` are single-instance modes. This is a real reduction in what a multi-replica deployment can run, and it is deliberate.
- No migration exists between storage backends (ADR-019), and none is added here.
