# Installation

> Looking for the operator image or Helm charts? See
> [Releases & Artifacts](releases.md) for every published artifact and its
> install command.

## Requirements

- Python 3.11 or higher
- Docker or Podman (for container MCP servers)

## Quick Install (Recommended)

```bash
curl -sSL https://mcp-hangar.io/install.sh | bash
```

This will install the latest version of MCP Hangar and set up your environment.

## Install from PyPI

```bash
pip install mcp-hangar
```

## Which line you get

`pip install mcp-hangar` resolves to **2.1.1**, the current stable release. It
is on a major line: 2.0.0 moved onto the MCP 2026-07-28 protocol generation and
the stable `mcp==2.0.0` SDK, and removed the last vendor integration from core.
2.1.0 makes the human-in-the-loop approval gate reachable — `approval_list` in a
`tools:` block now actually holds a call for a human — and adds a startup check
that refuses to boot when the configuration demands a subsystem the runtime
cannot reach. It is drop-in unless your config already carries `approval_list`;
see [Upgrade to 2.1.0](../upgrade.md#upgrade-to-210).

If you are coming from 1.6.x, read [Upgrade to 2.0.0](../upgrade.md)
first — there are two changes that need a decision before you upgrade, not
after: Slack approval delivery now needs an adapter you run yourself, and
approval resolution is authorized.

To stay on the older line while you plan that work, pin it:

```bash
pip install "mcp-hangar>=1.6,<2"      # the 1.6.x line
```

The 1.6.x line receives no new features. `--pre` is no longer needed for the v2
line — it is the default resolve.

## Install from Source (Monorepo)

MCP Hangar is organized as a monorepo:

```
mcp-hangar/
├── src/mcp_hangar/     # Python package (PyPI: mcp-hangar)
```

### Python Core Package

```bash
git clone https://github.com/mcp-hangar/mcp-hangar.git
cd mcp-hangar
pip install -e .
```

### Development Installation

```bash
git clone https://github.com/mcp-hangar/mcp-hangar.git
cd mcp-hangar

# Install with dev dependencies
pip install -e ".[dev]"

# Or use uv from root
make setup
```

## Docker

```bash
docker pull ghcr.io/mcp-hangar/mcp-hangar:2.1.1

# Run with config
docker run -v $(pwd)/config.yaml:/app/config.yaml:ro \
  ghcr.io/mcp-hangar/mcp-hangar:2.1.1
```

> The tag above pins the current stable release, matching what
> `pip install mcp-hangar` gives you. See
> [Releases & Artifacts](releases.md) for the authoritative version index.

## Verify Installation

```bash
mcp-hangar --version
```
