# MCP Hangar

[![CI - Core](https://github.com/mcp-hangar/mcp-hangar/actions/workflows/ci-core.yml/badge.svg)](https://github.com/mcp-hangar/mcp-hangar/actions/workflows/ci-core.yml)
[![CI - Operator](https://github.com/mcp-hangar/mcp-hangar-operator/actions/workflows/ci.yml/badge.svg)](https://github.com/mcp-hangar/mcp-hangar-operator/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-hangar)](https://pypi.org/project/mcp-hangar/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-mcp--hangar.io-blue)](https://mcp-hangar.io)

Production-grade MCP server registry with lazy loading, health monitoring, and container support.

## Repository Structure

The core is one package; the operator and the Helm charts are released from
their own repositories (see [Releases & Artifacts](getting-started/releases.md)):

| Package | Description | Location |
| --------- | ------------- | ---------- |
| **Core** | Python library (PyPI: `mcp-hangar`) | `src/mcp_hangar/` |

## Features

- **Lazy Loading** -- MCP servers start only when invoked, tools visible immediately
- **Container Support** -- Docker/Podman with auto-detection
- **MCP Server Groups** -- Load balancing with multiple strategies
- **Health Monitoring** -- Circuit breaker pattern with automatic recovery
- **Auto-Discovery** -- Detect MCP servers from Docker labels, K8s annotations, filesystem
- **REST API** -- Full CRUD API for MCP servers, groups, discovery, config, and auth
- **Log Streaming** -- MCP server logs via REST
- **RBAC** -- Role-based access control with tool-level policies
- **Automatic Retry** -- Built-in retry with exponential backoff for transient failures
- **Real-Time Progress** -- See operation progress while waiting
- **Rich Errors** -- Human-readable errors with recovery hints
- **Kubernetes Native** -- CRDs for declarative MCP server management

## Quick Start

**30 seconds to working MCP servers:**

```bash
curl -sSL https://mcp-hangar.io/install.sh | bash
export PATH="$HOME/.mcp-hangar/bin:$PATH"   # or open a new shell
mcp-hangar init -y
```

That's it. Restart your MCP client and you have filesystem, fetch, and memory MCP servers.

!!! info "What just happened?"
    **Install** - Installed `mcp-hangar` into a private venv in `~/.mcp-hangar` via uv or pip.
    **Init** - Created `~/.config/mcp-hangar/config.yaml` with the starter MCP servers,
    pinned their tools, and pointed the MCP clients it detected at Hangar.
    Your client starts `mcp-hangar serve` (stdio mode) itself.
    The `init -y` flag uses sensible defaults: detects runtimes (npx, uvx, Docker/Podman),
    configures the starter bundle (filesystem, fetch, memory), updates the detected clients
    (Claude Code, Cursor, Claude Desktop).

### Manual Installation

```bash
# Install
pip install mcp-hangar

# Interactive setup wizard
mcp-hangar init

# Start server by hand (your client normally does this)
mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve
```

### HTTP Mode

```bash
# Start with REST API (a non-loopback --host needs authentication)
mcp-hangar --config ~/.config/mcp-hangar/config.yaml serve --http --host 127.0.0.1 --port 8000

# REST API:  http://localhost:8000/api/mcp_servers/
```

## Documentation

- [Installation](getting-started/installation.md)
- [Quick Start Guide](getting-started/quickstart.md)
- [Architecture Overview](architecture/OVERVIEW.md)
- [Progressive Deployment Playbook](guides/DEPLOYMENT_PLAYBOOK.md)
- [REST API Guide](guides/REST_API.md)
- [The official MCP servers](guides/OFFICIAL_SERVERS.md)
- [Container Guide](guides/CONTAINERS.md)
- [Authentication & RBAC](guides/AUTHENTICATION.md)
- [Front-Door Mode & Per-Tenant Tool Governance](guides/FRONT_DOOR.md)
- [Egress Policy (MCPEgressPolicy)](guides/EGRESS_POLICY.md)
- [Approval delivery adapters](guides/APPROVAL_ADAPTERS.md)
- [Governed Tasks (Task Relay)](guides/GOVERNED_TASKS.md)
- [Observability](guides/OBSERVABILITY.md)

## Contributing

See [Contributing Guide](development/CONTRIBUTING.md) for development setup and guidelines.

## License

MIT - see [LICENSE](https://github.com/mcp-hangar/mcp-hangar/blob/main/LICENSE) for details.
