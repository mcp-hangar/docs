# 10 -- Discovery: Docker

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar, Docker or Podman
> **Time:** 10 minutes
> **Adds:** Auto-discover MCP servers from Docker container labels

## The Problem

You have MCP servers running as Docker containers. You don't want to manually update `config.yaml` every time a container starts or stops. You want Hangar to detect them automatically.

## The Config

```yaml
# config.yaml -- Recipe 10: Docker Discovery
discovery:                               # NEW: discovery configuration
  enabled: true                          # NEW: enable auto-discovery
  refresh_interval_s: 30                 # NEW: scan every 30 seconds
  auto_register: false                   # NEW: require manual approval

  sources:                               # NEW: discovery sources
    - type: docker                       # NEW: Docker source
      mode: additive                     # NEW: only add, never remove
```

## Try It

1. Start an MCP server container with labels:

   ```bash
   docker run -d --name my-mcp-server \
     -l mcp.hangar.enabled=true \
     -l mcp.hangar.name=docker-math \
     -l mcp.hangar.mode=http \
     -l mcp.hangar.port=8080 \
     my-mcp-server:latest
   ```

2. Start Hangar:

   ```bash
   mcp-hangar serve --http --host 127.0.0.1 --port 8000
   ```

3. Scan. A source scans on its own every `discovery.refresh_interval_s`, on
   the instance holding the management lease (see
   [25](25-multiple-replicas.md)) -- the log line is `discovery_cycle_complete`.
   To do it now, read the source's id and ask:

   ```bash
   curl -s http://localhost:8000/api/discovery/sources    # each source carries an `id`
   curl -X POST http://localhost:8000/api/discovery/sources/<id>/scan
   ```

   *Since 2.5.0.* The id of a source declared in `config.yaml` is derived from
   its type, so it is the same after a restart and safe to keep in a script.
   Earlier releases listed configured sources without an `id` and answered
   `404` on this route for every id you could obtain.

4. Check pending MCP servers:

   ```bash
   curl http://localhost:8000/api/discovery/pending
   ```

   ```json
   {"pending": [{"name": "docker-math", "source_type": "docker", "mode": "remote",
                 "connection_info": {"endpoint": "http://172.17.0.3:8080/mcp"},
                 "metadata": {}, "fingerprint": "...", "discovered_at": "...",
                 "last_seen_at": "...", "ttl_seconds": 300, "is_expired": false}]}
   ```

   The key is `source_type`, not `source`.

5. Approve the MCP server:

   ```bash
   curl -X POST http://localhost:8000/api/discovery/approve/docker-math
   ```

6. Verify it's registered:

   ```bash
   mcp-hangar status
   ```

   ```
   docker-math    COLD
   ```

## What Just Happened

The Docker discovery source connects to the Docker socket and lists containers with `mcp.hangar.enabled=true` labels. In `additive` mode, it only adds new MCP servers -- never removes existing ones. With `auto_register: false`, discovered MCP servers go to a pending queue for manual approval. Omit the key and they are registered on discovery: the default is `true`.

Set `auto_register: true` if you trust all labeled containers and want zero-touch registration.

## With More Than One Hangar

*Since 2.5.0*, discovery runs only on the replica holding the management lease,
and each replica reads its own Docker socket -- so the containers it can see are
the ones on its node. Give every replica the discovery configuration, not just
one: the holder can be any of them. See
[11 -- Kubernetes discovery](11-discovery-kubernetes.md#with-more-than-one-hangar)
for the same rule stated in full, and
[25 -- Running More Than One Replica](25-multiple-replicas.md).

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `discovery.enabled` | bool | `false` | Enable auto-discovery |
| `discovery.refresh_interval_s` | int | `30` | Seconds between scans |
| `discovery.auto_register` | bool | **`true`** | Register a discovered server without approval. The default registers -- set it to `false`, as this recipe does, if you want the pending queue |
| `discovery.sources[].type` | string | -- | `docker`, `filesystem`, `kubernetes`, `entrypoint` |
| `discovery.sources[].mode` | string | -- | `additive` (add only) or `authoritative` (add and remove) |

### Docker Labels

| Label | Required | Default | Description |
|-------|----------|---------|-------------|
| `mcp.hangar.enabled` | Yes | -- | Must be `"true"` |
| `mcp.hangar.name` | No | Container name | MCP Server name |
| `mcp.hangar.mode` | No | `container` | MCP Server mode |
| `mcp.hangar.port` | No | `8080` | MCP Server port |
| `mcp.hangar.group` | No | -- | Auto-add to group |

## What's Next

Docker discovery works for local and CI environments. For Kubernetes, you need annotation-based discovery.

--> [11 -- Discovery: Kubernetes](11-discovery-kubernetes.md)
