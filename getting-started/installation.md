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

## Installing the v2 preview (release candidate)

The v2 line is a release candidate (`2.0.0rc3`, built on the stable `mcp==2.0.0`)
and is opt-in. A normal `pip install mcp-hangar` still lands on stable **1.6.3** —
pip does not resolve to a prerelease unless you ask for one.

```bash
pip install --pre mcp-hangar          # newest prerelease (the v2 line)
pip install "mcp-hangar==2.0.0rc3"    # pin the exact release candidate
```

`--pre` opts the whole resolve into prereleases; the pinned `==2.0.0rc3` form
takes exactly that build. Both leave a plain `pip install mcp-hangar` on 1.6.3.

> What the v2 preview adds — governed task relay-with-governance (ADR-014),
> landing in 2.0, not on the 1.6.x line — is summarized under
> [v2 preview (release candidate)](releases.md#v2-preview-release-candidate) in Releases &
> Artifacts.

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
docker pull ghcr.io/mcp-hangar/mcp-hangar:1.6.3

# Run with config
docker run -v $(pwd)/config.yaml:/app/config.yaml:ro \
  ghcr.io/mcp-hangar/mcp-hangar:1.6.3
```

> The tag above pins the current stable release. See
> [Releases & Artifacts](releases.md) for the authoritative version index.

## Verify Installation

```bash
mcp-hangar --version
```
