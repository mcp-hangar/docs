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

   > **Preview.** Triggering a scan and the other source-management routes
   > (register/update/delete/enable/disable) ship in 2.5.0 as **Preview**, not
   > GA — the behaviour may still change. Those responses carry the header
   > `X-Hangar-Preview: discovery-source-management`. Listing sources and the
   > approval workflow are stable.

4. Check pending MCP servers:

   ```bash
   curl http://localhost:8000/api/discovery/pending
   ```

   ```json
   {"pending": [{"name": "docker-math", "source_type": "docker", "mode": "http",
                 "connection_info": {"host": "172.17.0.3", "port": 8080, "path": "/mcp",
                                     "endpoint": "http://172.17.0.3:8080/mcp"},
                 "metadata": {"container_id": "...", "container_name": "my-mcp-server",
                              "image": "my-mcp-server:latest", "status": "running",
                              "runtime_addresses": ["172.17.0.3"]},
                 "fingerprint": "...", "discovered_at": "...", "last_seen_at": "...",
                 "ttl_seconds": 90, "is_expired": false}]}
   ```

   The key is `source_type`, not `source`. The endpoint is the container's
   published host port when it has one (`-p`), otherwise its network IP, plus
   the `mcp.hangar.path` label, `/mcp` by default. Before 2.28.0 the Docker
   source had no path label and the endpoint carried no path, so a server that
   serves MCP at `/mcp` answered the first call with
   `MCP initialization failed: HTTP error: 404`.

5. Approve the MCP server:

   ```bash
   curl -X POST http://localhost:8000/api/discovery/approve/docker-math
   ```

   ```json
   {"approved": true, "mcp_server": "docker-math", "status": "registered"}
   ```

   The route approves a server in the pending queue, held by
   `auto_register: false`, or in **quarantine** (`GET
   /api/discovery/quarantined`), where it failed validation. A name in neither
   answers `"approved": false` with
   `"error": "McpServer not found in quarantine or pending"`. Before 2.28.0 it
   looked in quarantine only, so a pending server could not be approved.

6. Verify it's registered, in `remote` mode. With `auto_register: true` it
   appears here without the approval step:

   ```bash
   curl http://localhost:8000/api/mcp_servers/
   ```

   ```json
   {"mcp_servers": [{"mcp_server_id": "docker-math", "state": "cold", "mode": "remote",
                     "alive": false, "tools_count": 0, "health_status": "unknown",
                     "tools_predefined": false, "dead": null,
                     "description": "Discovered from docker"}]}
   ```

   `mcp-hangar status` shows it too when it reaches the gateway: it asks
   `MCP_HANGAR_URL`, else `MCP_HTTP_HOST` (default `127.0.0.1`) on
   `MCP_HTTP_PORT` or ports 8000 and 8080, and falls back to `config.yaml`
   alone when nothing answers.

## What Just Happened

The Docker discovery source connects to the Docker socket and lists containers with `mcp.hangar.enabled=true` labels, stopped and never-started ones included. In `additive` mode, it only adds new MCP servers -- never removes existing ones. With `auto_register: false`, discovered MCP servers go to a pending queue for manual approval. Omit the key and they are registered on discovery: the default is `true`.

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
| ----- | ------ | --------- | ------------- |
| `discovery.enabled` | bool | `false` | Enable auto-discovery |
| `discovery.refresh_interval_s` | int | `30` | Seconds between scans |
| `discovery.auto_register` | bool | **`true`** | Register a discovered server without approval. The default registers -- set it to `false`, as this recipe does, if you want the pending queue |
| `discovery.sources[].type` | string | -- | `docker`, `filesystem`, `kubernetes`, `entrypoint` |
| `discovery.sources[].mode` | string | `additive` | `additive` (add only) or `authoritative` (add, and remove a server no longer reported once its TTL has passed; see [Discovery Modes](../guides/DISCOVERY.md#discovery-modes)) |
| `discovery.sources[].allowed_mount_paths` | list | -- | Docker only: host directories a `mcp.hangar.volumes` label may mount from |

### Docker Labels

| Label | Required | Default | Description |
| ------- | ---------- | --------- | ------------- |
| `mcp.hangar.enabled` | Yes | -- | Must be `"true"` |
| `mcp.hangar.name` | No | Container name | MCP Server name |
| `mcp.hangar.mode` | No | `container` | `container` (Hangar runs the image) or `http`/`sse` (Hangar connects to the running container) |
| `mcp.hangar.port` | No | `8080` | Container port, for `http`/`sse` mode |
| `mcp.hangar.path` | No | `/mcp` | The MCP endpoint's path, for `http`/`sse` mode |
| `mcp.hangar.ttl` | No | `90` | Seconds an `authoritative` source keeps the server after it stops being reported |
| `mcp.hangar.read-only` | No | `true` | `container` mode: read-only root filesystem; `"false"` opts out |
| `mcp.hangar.volumes` | No | -- | `container` mode: comma-separated mounts, honoured only under the source's `allowed_mount_paths`; otherwise the container is not registered |
| `mcp.hangar.command` | No | -- | `container` mode: accepted, but not passed to the container today |

There is no `group` label.

## What's Next

Docker discovery works for local and CI environments. For Kubernetes, you need annotation-based discovery.

--> [11 -- Discovery: Kubernetes](11-discovery-kubernetes.md)
