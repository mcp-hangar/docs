# 20 -- Read-Only Rootfs & Controlled Writes

> **Prerequisite:** [13 -- Production Checklist](13-production-checklist.md)
> **You will need:** Running Hangar, Docker or Podman
> **Time:** 20 minutes
> **Adds:** A read-only-by-default deployment where writes are granted only
> where genuinely needed, and the audit/event trail is durable or fails fast

## The Problem

A production MCP fleet is a soft target: a compromised provider that can write
to its own root filesystem can drop a binary, tamper with libraries, or persist
between restarts. The safe default is a **read-only root filesystem** for every
container, and a **writable volume granted only to the specific stateful
providers that genuinely need one**.

Two failure modes bite operators here:

1. You harden everything read-only, then a stateful provider (a database, a
   memory store) fails at runtime with `EROFS` -- *"Read-only file system"* --
   because it has nowhere to write.
2. You mount Hangar itself read-only and its SQLite audit/event store silently
   turns into an in-memory store, so your audit trail evaporates on the next
   restart.

This recipe shows the boundary: read-only by default, a `:rw` volume exactly
where required, and an event store that is either durable or refuses to start.

## The Config

```yaml
# config.yaml -- Recipe 20: read-only rootfs + controlled writes

mcp_servers:

  # Stateless provider -- read-only, no volume, fully sandboxed.
  # read_only defaults to true; network none is the default. Both are shown
  # here for clarity.
  fetch:
    mode: container
    image: localhost/mcp-fetch:latest
    read_only: true                        # NEW: read-only root filesystem (default)
    network: none                          # NEW: no network namespace (default)
    resources:
      memory: 256m                         # NEW: memory ceiling
      cpu: "0.5"                           # NEW: CPU ceiling
    idle_ttl_s: 180

  # Stateful provider -- STILL read-only root, but one writable volume where
  # the process genuinely persists data. Everything else stays locked down.
  sqlite:
    mode: container
    image: localhost/mcp-sqlite:latest
    read_only: true                        # NEW: root stays read-only
    volumes:
      - "/srv/hangar/sqlite:/data:rw"      # NEW: the ONLY writable path (absolute)
    network: bridge                        # NEW: this provider needs egress
    idle_ttl_s: 300

# Durable audit/event store. On a read-only Hangar deploy the path below MUST
# be a writable mount, or startup fails fast (see "Durability", below).
event_store:
  enabled: true
  driver: sqlite                           # NEW: durable driver
  path: /app/data/events.db                # NEW: must be writable
  allow_memory_fallback: false             # NEW: never silently lose the audit trail
```

## Try It

1. Provision the one writable host directory the stateful provider needs, and
   the directory that backs the durable event store:

   ```bash
   sudo mkdir -p /srv/hangar/sqlite /srv/hangar/events
   ```

2. Start Hangar with a read-only root filesystem, granting write access only to
   the event-store directory (mounted at `/app/data`, which the image owns as
   the non-root `hangar` user):

   ```bash
   docker run --rm \
     --read-only \
     --tmpfs /tmp:rw,noexec,nosuid,size=64m \
     --security-opt no-new-privileges \
     -v /srv/hangar/events:/app/data:rw \
     -v "$PWD/config.yaml:/app/config.yaml:ro" \
     -p 8000:8080 \
     mcp-hangar:1.6.0 serve --http --port 8080
   ```

3. Confirm the event store is durable. `/health/ready` includes the
   `event_store_durability` check; a durable store returns `200`:

   ```bash
   curl -s http://localhost:8000/health/ready
   ```

   ```json
   {"status": "ready", "checks": {"event_store_durability": "healthy"}}
   ```

4. Now prove the fail-closed behaviour. Point the event store at a path under
   the read-only root (no writable mount) and start again:

   ```bash
   docker run --rm --read-only \
     --tmpfs /tmp:rw,noexec,nosuid,size=64m \
     -e MCP_JSON_LOGS=true \
     mcp-hangar:1.6.0 serve --http
   ```

   Startup aborts instead of silently degrading:

   ```
   EventStoreConfigurationError: event store path '/app/data/events.db' is not
   writable ([Errno 30] Read-only file system); set event_store.driver: memory
   to explicitly opt into a non-durable store, or
   event_store.allow_memory_fallback: true to accept a non-durable in-memory
   fallback
   ```

5. Prove the same boundary for a stateful provider. Remove its `:rw` volume and
   invoke a tool that writes -- the provider fails with `EROFS`:

   ```
   sqlite3.OperationalError: unable to open database file
   OSError: [Errno 30] Read-only file system: '/data/store.db'
   ```

   Restore the `volumes:` entry and the write succeeds -- writes are now
   confined to `/data`, and nowhere else.

## What Just Happened

Hangar launches container providers through a hardened command builder. For
every container it applies the same sandbox, independent of the provider:

- `--read-only` when `read_only: true` (the **default** -- you opt *out*, never
  in).
- `--tmpfs /tmp:rw,noexec,nosuid,size=64m` so a locked-down root still has a
  scratch `/tmp` that never touches the image layer.
- `--security-opt no-new-privileges` so no child process can gain privileges via
  setuid binaries.
- `--network none` by default (`bridge`/`host` only when a provider declares it).
- `--memory` and `--cpus` from `resources:` (defaults `512m` / `1.0`).

The only writes a provider can perform go to the paths you list under
`volumes:`, in `host:container:rw` form with an **absolute** host path. A
stateful provider without such a mount hits `EROFS` the moment it tries to
persist -- which is the point: the failure is loud and local, not a silent
tamper surface.

The event store enforces the same discipline for Hangar's own audit trail. When
`driver: sqlite` is configured but the path is not writable (the classic
read-only-deploy mistake), initialization raises `EventStoreConfigurationError`
and Hangar **fails fast** rather than swapping in a non-durable in-memory store
and quietly losing history. A non-durable store is only ever used when you ask
for it explicitly -- either `driver: memory`, or `allow_memory_fallback: true`.
If the fallback is taken, the degraded posture is recorded and the
`event_store_durability` readiness check turns critical, so `/health/ready`
reports `503` and your orchestrator refuses to route traffic to a node that has
lost durability.

Finally, the stock Hangar image runs as a **non-root** user (`hangar`), and its
writable data directory is `/app/data`. Mount your durable volume there and the
non-root process can write to it while everything else stays read-only.

## Where To Grant Writes (and Where Not)

| Component | Root filesystem | Writable mount | Why |
|-----------|-----------------|----------------|-----|
| Stateless provider (fetch, calculators) | read-only | none | Never persists; a write is a red flag |
| Stateful provider (sqlite, memory) | read-only | one `:rw` volume | Persists to a single audited path |
| Hangar event store | read-only | `/app/data` (`:rw`) | Durable audit/event-sourcing trail |
| Any provider's `/tmp` | read-only | tmpfs (automatic) | Scratch space, wiped on exit |

Rule of thumb: default everything to read-only, then add exactly one `:rw`
volume per component that has a durability requirement you can name. If you
cannot name what it persists, it does not get a volume.

## Verify

- Read-only holds: `docker inspect --format '{{.HostConfig.ReadonlyRootfs}}'
  <container>` returns `true` for every provider container.
- Writes are confined: the only `:rw` bind mounts in `docker inspect` are the
  ones you declared; `/tmp` is a tmpfs.
- Durability is live: `/health/ready` shows `event_store_durability: healthy`;
  intentionally breaking the mount flips it to `503`.
- Fail-fast works: launching with an unwritable `event_store.path` and
  `allow_memory_fallback: false` aborts startup with
  `EventStoreConfigurationError`.

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mcp_servers.<id>.read_only` | bool | `true` | Read-only container root filesystem |
| `mcp_servers.<id>.volumes` | list | `[]` | `host:container[:ro\|rw]`; host path absolute |
| `mcp_servers.<id>.network` | string | `none` | `none`, `bridge`, or `host` |
| `mcp_servers.<id>.resources.memory` | string | `512m` | Memory ceiling (`--memory`) |
| `mcp_servers.<id>.resources.cpu` | string | `1.0` | CPU ceiling (`--cpus`) |
| `event_store.driver` | string | `sqlite` | `sqlite` (durable) or `memory` (non-durable) |
| `event_store.path` | string | `data/events.db` | SQLite file; must be writable |
| `event_store.allow_memory_fallback` | bool | `false` | Opt in to a non-durable fallback |

## What's Next

You now have a read-only baseline with named, audited write surfaces. Wire the
`/health/ready` durability signal into your orchestrator's readiness gate so a
node that loses durability is pulled from rotation automatically.

--> [13 -- Production Checklist](13-production-checklist.md)
