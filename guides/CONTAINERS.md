# Container MCP servers

Run MCP servers in Docker or Podman containers.

## Quick Start

Nothing to build: the servers from
[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
are published as images by Docker.

```bash
# Pull the official images
podman pull docker.io/mcp/filesystem:latest
podman pull docker.io/mcp/memory:latest
podman pull docker.io/mcp/fetch:latest

# Create data directories
mkdir -p data/memory data/filesystem
```

> Hangar used to ship `docker/Dockerfile.*` for these, and this guide gave the
> `podman build` commands. Two of them repackaged the same official npm
> package, one repackaged a third-party fork, and nothing in the repository
> built any of them -- so they were deleted (core#1095). There is no official
> `sqlite` server: that one was a third-party package whose upstream is
> archived, and it has no replacement here.

For a server you drive as a **subprocess** rather than a container, prefer the
packages over the images -- `npx -y @modelcontextprotocol/server-filesystem`,
`uvx mcp-server-fetch`. They are released continuously, while the published
container images for `filesystem` and `memory` were last rebuilt in 2025.

## Configuration

```yaml
mcp_servers:
  filesystem:
    mode: container
    image: docker.io/mcp/filesystem:latest
    volumes:
      - "/absolute/path/to/data:/data:rw"
    network: bridge
    idle_ttl_s: 300
    resources:
      memory: 512m
      cpu: "1.0"
```

> **Important**: Always use absolute paths. Relative paths (`./data`, `${PWD}`) fail when MCP clients start the server from different directories.

### Options

| Option | Description | Default |
| -------- | ------------- | --------- |
| `image` | Container image | required |
| `volumes` | Mount points (`host:container:mode`) | `[]` |
| `env` | Environment variables | `{}` |
| `network` | Network mode: `none`, `bridge`, `host` | `none` |
| `network_mode` | Alias for `network` (Docker Compose compatibility) | `none` |
| `read_only` | Read-only root filesystem | `true` |
| `resources.memory` | Memory limit | `512m` |
| `resources.cpu` | CPU limit | `1.0` |

#### Network Modes

- **`none`** (default): No network access. Most secure, use for MCP servers that don't need external connectivity.
- **`bridge`**: Isolated bridge network. Container can reach external services but is isolated from host network.
- **`host`**: Share host network namespace. Required when MCP server needs to connect to services on localhost or has complex networking requirements.

```yaml
# MCP Server that needs to connect to local Prometheus/VictoriaMetrics
prometheus:
  mode: docker
  image: ghcr.io/pab1it0/prometheus-mcp-server:latest
  network_mode: host  # or network: host
  env:
    PROMETHEUS_URL: "https://victoriametrics.example.com"
```

### Custom Build

```yaml
mcp_servers:
  custom:
    mode: container
    build:
      dockerfile: docker/Dockerfile.custom
      context: .
      tag: my-image:latest
```

## Available Images

These are the servers from
[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
that Docker publishes. There is **no official SQLite server** -- the upstream
one is archived -- so this guide no longer lists one.

### Memory (Knowledge Graph)

```yaml
memory:
  mode: container
  image: docker.io/mcp/memory:latest
  volumes:
    - "/path/to/data:/app/data:rw"
```

Tools: `create_entities`, `create_relations`, `search_nodes`, `read_graph`

```python
hangar_call(calls=[{"mcp_server": "memory", "tool": "create_entities",
                    "arguments": {"entities": [
                        {"name": "Alice", "entityType": "Person", "observations": ["Engineer"]}
                    ]}}])
```

### Filesystem

```yaml
filesystem:
  mode: container
  image: docker.io/mcp/filesystem:latest
  volumes:
    - "/path/to/sandbox:/data:rw"
```

Tools: `read_file`, `write_file`, `list_directory`

### Fetch

```yaml
fetch:
  mode: container
  image: docker.io/mcp/fetch:latest
  network: bridge
```

Tools: `fetch`

```python
hangar_call(calls=[{"mcp_server": "fetch", "tool": "fetch",
                    "arguments": {"url": "https://api.example.com/data"}}])
```

## Troubleshooting

### Container won't start

```bash
# Verify image
podman images docker.io/mcp/filesystem

# Test manually
echo '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{}}' | \
  podman run --rm -i -v /path/to/data:/data:rw docker.io/mcp/filesystem:latest
```

### Data not persisting

1. Use absolute paths
2. Check host directory permissions
3. Verify mount:

   ```bash
   podman run --rm -v /path/to/data:/data:rw --entrypoint sh \
     docker.io/mcp/filesystem:latest -c "ls -la /data"
   ```

### Permission denied

```bash
chmod 777 data/sqlite
```

Or set `MCP_CI_RELAX_VOLUME_PERMS=true`.

## Environment Variables

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `MCP_CONTAINER_RUNTIME` | auto | Force `podman` or `docker` |
| `MCP_CI_RELAX_VOLUME_PERMS` | `false` | Chmod 777 on volumes (CI) |
