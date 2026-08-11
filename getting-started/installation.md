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

### Extras you may need

Two optional dependencies are load-bearing, and a plain `pip install
mcp-hangar` installs neither:

```bash
pip install "mcp-hangar[postgres]"      # persistence.backend: postgresql
pip install "mcp-hangar[kubernetes]"    # the kubernetes discovery source
```

`[postgres]` brings the PostgreSQL driver, so it is required for
`persistence.backend: postgresql` — and therefore for any replica set, since a
declared cluster refuses to start on a file-backed backend. `[kubernetes]`
brings the client the Kubernetes discovery source imports; without it the source
cannot be constructed and discovers nothing. The published image already
installs both, so this applies to a pip install only.

## Which line you get

`pip install mcp-hangar` resolves to **2.5.3**, the current stable release. It
is on a major line: 2.0.0 moved onto the MCP 2026-07-28 protocol generation and
the stable `mcp==2.0.0` SDK, and removed the last vendor integration from core.
2.1.0 makes the human-in-the-loop approval gate reachable — `approval_list` in a
`tools:` block now actually holds a call for a human — and adds a startup check
that refuses to boot when the configuration demands a subsystem the runtime
cannot reach. It is drop-in unless your config already carries `approval_list`;
see [Upgrade to 2.1.0](../upgrade.md#upgrade-to-210).

2.5.0 is what you actually land on. It makes storage one decision —
`persistence.backend: sqlite | postgresql` picks one backend for every persisted
concern, or the selection is refused — and adds multi-replica coordination: a
`coordination:` block declares that several replicas are one gateway, exactly
one instance holds the management lease, and PostgreSQL is required there. Local
modes are refused on two separate axes: a server *declared* in `config.yaml` has
to be in `remote` mode once a `coordination:` block exists, while *registering* a
`subprocess`, `docker` or `container` server through the API is refused (HTTP
422) whenever the storage can be shared — which a single gateway on
`persistence.backend: postgresql` already is, block or no block. It also ships
discovery source management as Preview: nothing is gated on a header, but every
mutating response carries `X-Hangar-Preview: discovery-source-management` so a
client can detect the preview status. And it re-checks SSRF policy at connect
time rather than only at registration — a check that on 2.5.0 was lost whenever
a gateway restarted, and that **2.5.1** restores for the servers already
registered; if you are running 2.5.0, see
[Upgrade to 2.5.1](../upgrade.md#upgrade-to-251). **2.5.2 is the one to be on
if you select a storage backend at all**: on 2.5.0 and 2.5.1 an auth-enabled
gateway could not start on `persistence.backend`, because the auth tables were
never created — see [Upgrade to 2.5.2](../upgrade.md#upgrade-to-252).
**2.5.3** is drop-in on top of that, and two of its fixes are visible from
outside: `prompts/list` and `resources/list` now answer `-32601` instead of an
empty list, because the gateway no longer advertises capabilities it does not
serve; and an upstream that registers tools on initialization has them
discovered for the first time, so its catalogue can grow — see
[Upgrade to 2.5.3](../upgrade.md#upgrade-to-253).
Selecting a backend is opt-in, but those two changes land
on every deployment regardless, as do interpolation (a `${VAR}` with no value
and no `:-default` now fails the whole boot, not just the `auth` sub-block), the
`auth bootstrap-admin` command, TLS, and the backup endpoint;
see [Upgrade to 2.5.0](../upgrade.md#upgrade-to-250) and
[Running more than one replica](../cookbook/25-multiple-replicas.md).

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
docker pull ghcr.io/mcp-hangar/mcp-hangar:2.5.3

# Run with config
docker run -v $(pwd)/config.yaml:/app/config.yaml:ro \
  ghcr.io/mcp-hangar/mcp-hangar:2.5.3
```

> The tag above pins the current stable release, matching what
> `pip install mcp-hangar` gives you. See
> [Releases & Artifacts](releases.md) for the authoritative version index.

## Verify Installation

```bash
mcp-hangar --version
```
