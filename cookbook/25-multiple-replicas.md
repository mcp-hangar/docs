# Running more than one replica

*Since 2.5.0.*

Until 2.5.0 the honest advice was to run one Hangar and make its restart fast.
More than one replica did not fail loudly -- it produced a gateway that
disagreed with itself: a server registered on one replica was invisible to the
others, a session suspended by a detection rule was still served by the rest,
and each replica ran its own discovery loop, so one could deregister what
another had just registered.

This page is what changed, what it requires, and what it still costs.

## What a replica set requires

**One PostgreSQL that every replica shares.** This is not a recommendation. A
`coordination:` block on a file-backed backend refuses to start, because
replicas that cannot share storage are not one gateway -- each would hold its
own fleet and its own lease, and they would never notice each other.

**`remote`-mode servers.** `subprocess` and `docker` do not describe a server
the gateway talks to; they describe one it *runs*, as a child process with its
stdio attached. No peer can reach it, so a replica serving a call to such a
server starts its own copy, with its own mounted volumes. Registering one is
refused in a coordinated deployment, and starting one is refused on a follower.

```yaml
persistence:
  backend: postgresql
  postgresql:
    host: db.internal.example
    database: mcp_hangar
    user: hangar
    password: ${HANGAR_DB_PASSWORD}

coordination:
  lease_ttl_s: 15
  renew_interval_s: 5
  renew_deadline_s: 10

mcp_servers:
  weather:
    mode: remote
    endpoint: http://weather.internal:8080/mcp
```

In Kubernetes, give each pod a recognisable identity from the downward API:

```yaml
env:
  - name: HANGAR_INSTANCE_LABEL
    valueFrom:
      fieldRef: {fieldPath: metadata.name}
```

It is a label, not the identity -- a per-process suffix is always appended, so
replicas rolled from one ConfigMap cannot share an id.

## What every replica does, and what only one does

Every replica **serves**: tool calls, the API, the MCP surface. Serving is never
gated on anything below.

Exactly one replica **manages**: discovery, garbage collection, TTL
deregistration, and the metric-snapshot worker. It holds a lease -- a row in the
shared database with a expiry and a generation -- and the others wait.

Everything else is a *projection*: fleet membership, the tool catalogue, risk
scores, session suspensions and the websocket event feed are rebuilt on every
replica from the shared event log, so what you get back does not depend on which
pod answered.

## Checking it

```
GET /api/system
```

```json
{
  "system": {
    "instance": {
      "instance_id": "hangar-7f9c4d2b1a-a3f19c",
      "coordinates_with_peers": true,
      "manages_fleet": true,
      "storage_is_shareable": true,
      "rate_limits_are_per_instance": true
    }
  }
}
```

Ask each pod directly rather than through the Service -- the point of the field
is that replicas can differ. Exactly one should answer `manages_fleet: true`.
**Two answering `false` while none answers `true` is a fleet with nothing
converging it**, which is worth being able to read directly rather than
inferring from what has stopped happening.

`coordinates_with_peers: false` on a deployment you believe is a cluster means
the storage is not shared -- each pod is its own gateway.

## What it costs

**Rate limits are counted per instance.** Three replicas admit three times the
configured rate. Dividing the number by the replica count drifts exactly when it
matters -- a rollout runs N+1 replicas and a failure runs N-1 -- and a shared
token bucket would put a database round trip on the path of every call. A
fleet-wide limit belongs at the ingress, where the fleet has one entrance.

**Anything travelling by the log lags by a poll interval.** A session suspended
on one replica holds there immediately and on its peers within a couple of
seconds. A replica that joins *after* a suspension does not inherit it.

**There is a window with no manager.** When the holder dies without releasing
the lease, nothing manages the fleet until the tenure expires -- fifteen seconds
by default. Serving continues throughout. A graceful shutdown releases the
lease, so a rolling update hands over in seconds rather than waiting out the
TTL.

**Circuit breakers and lifecycle state stay local.** Each replica decides for
itself whether it can reach an upstream, because a single replica with a network
problem must not cut a healthy server off from the other two. The cost is that
each discovers an outage independently.

## Rolling updates

Two versions run against one database for the length of the rollout. Hangar's
own schema changes are compatible with the previous release for at least one
version, and yours should be too if you extend it.

One consequence is worth knowing: during a rollout a newer replica can see an
event from an older one whose side effects the older version did not write. The
newer replica declines to guess and says so (`fleet_projection_no_record`)
rather than inventing a configuration. It resolves when the rollout completes.

## If something looks wrong

| Symptom | Cause |
|---|---|
| Every pod answers `manages_fleet: true` | the storage is not shared; check `storage_is_shareable` |
| No pod answers `true` | the database is unreachable, or the lease is held by a pod that has stopped -- it clears within the TTL |
| `fleet_writer_absent` in the logs | no durable config repository was in use; registrations are not being written down |
| A server exists on one pod only | the tail is stalled -- look for `event_tailer_read_failed` |
| `LocalModeNotOwnedError` | a `subprocess` or `docker` server in a coordinated deployment; use `remote` |

## See also

- [ADR-020](../adr/ADR-020-high-availability.md) -- the decisions behind this,
  their failure modes, and what is assumed rather than enforced
- [ADR-019](../adr/ADR-019-one-storage-decision-two-backends.md) -- why storage
  is one decision
- [Hardening a public gateway](23-harden-public-gateway.md)
