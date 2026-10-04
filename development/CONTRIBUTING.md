# Contributing

## Setup

```bash
git clone https://github.com/mcp-hangar/mcp-hangar.git
cd mcp-hangar

# Install with dev dependencies
uv sync --extra dev

# Or with pip
pip install -e ".[dev]"

# Or use root Makefile
make setup
```

## Repository Structure

MCP Hangar is **multi-repo**, not a monorepo (see ADR-009 for the release
topology this implies). The org has separate repos per shippable artifact:

- `mcp-hangar/mcp-hangar` -- Python core (PyPI: `mcp-hangar`). This is the repo
  you cloned in Setup above, and what the rest of this guide describes.
- `mcp-hangar/mcp-hangar-operator` -- Kubernetes operator (Go).
- `mcp-hangar/helm-charts` -- the `mcp-hangar` and `mcp-hangar-operator` Helm
  charts.
- `mcp-hangar/docs` -- this documentation site.
- `mcp-hangar/mcp-hangar-website` -- the marketing site.

Each has its own CONTRIBUTING guide, CI, and (per ADR-009) its own release
lane. This document only covers `mcp-hangar/mcp-hangar`.

Top-level layout of this repo:

```
mcp-hangar/
├── src/mcp_hangar/       # Python package (PyPI: mcp-hangar) -- MIT
│   ├── auth/             # RBAC, API key, JWT/OIDC
│   ├── approvals/        # Human-in-the-loop approval gate for tool calls
│   ├── bootstrap/        # DI composition root, module loading
│   ├── compliance/       # SIEM export (CEF, LEEF, JSON-lines)
│   ├── integrations/     # Partner integrations (Langfuse adapter)
│   ├── domain/           # DDD domain layer (see below)
│   ├── application/      # Application layer (see below)
│   ├── infrastructure/   # Infrastructure adapters (see below)
│   ├── observability/    # Tracing, metrics, health (see below)
│   ├── server/           # MCP server module (see below)
│   └── fastmcp_server/   # MCP-over-HTTP server (FastMCP-based)
├── tests/                # Python tests
├── changelog.d/          # one changelog fragment per PR
├── upgrade.d/            # one upgrade note per change a reader must act on
├── docs/                 # internal architecture/design docs (not this docs
│                         # site -- that's the separate docs repo)
├── examples/             # Quick starts, OTEL recipes
├── fuzz/                 # Fuzz targets (ClusterFuzzLite)
├── security/             # Seccomp profiles, network policies
├── scripts/              # Dev/release tooling
└── Makefile              # Root orchestration
```

There is no `packages/` directory in this repo: the operator and the Helm
charts live in the separate repos listed above.

## Python Core Structure

```
src/mcp_hangar/
├── domain/           # DDD domain layer
│   ├── model/        # Aggregates, entities
│   ├── services/     # Domain services
│   ├── events/       # Domain events
│   ├── contracts/    # Interfaces consumed by src/mcp_hangar/
│   └── exceptions.py
├── application/      # Application layer
│   ├── commands/     # CQRS commands
│   ├── queries/      # CQRS queries
│   ├── ports/        # Port interfaces consumed by src/mcp_hangar/
│   └── sagas/
├── infrastructure/   # Infrastructure adapters
│   └── observability/  # OTLPAuditExporter
├── observability/    # Conventions, tracing, metrics, health
├── server/           # MCP server module
│   ├── bootstrap/    # DI composition root
│   ├── config.py     # Configuration loading
│   ├── state.py      # Global state management
│   └── tools/        # MCP tool implementations
├── stdio_client.py   # JSON-RPC client
└── gc.py             # Background workers
```

## Licensing

- **All code** -- MIT. See [LICENSE](../LICENSE).
- Core and former enterprise code live in `src/mcp_hangar/`; imports stay within package boundaries.

## Code Style

```bash
ruff check src tests --fix
ruff format src tests
mypy src/mcp_hangar
```

### Conventions

| Item | Style |
| ------ | ------- |
| Classes | `PascalCase` |
| Functions | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Events | `PascalCase` + past tense (`McpServerStarted`) |

### Type Hints

Required for all new code. Use Python 3.11+ built-in generics:

```python
def invoke_tool(
    self,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    ...
```

## Testing

```bash
uv run pytest tests/unit -q
uv run pytest tests/unit --cov=mcp_hangar --cov-report=html

# Or from root
make test
```

Target: >80% coverage on new code.

### Writing Tests

```python
def test_tool_invocation():
    # Arrange
    mcp_server = McpServer(mcp_server_id="test", mode="subprocess", command=[...])

    # Act
    result = mcp_server.invoke_tool("add", {"a": 1, "b": 2})

    # Assert
    assert result["result"] == 3
```

## Pull Requests

See [Git Flow](GIT_FLOW.md) for branching conventions, merge strategy, and commit scopes.

1. Create feature branch
2. Make changes following style guidelines
3. Add tests
4. Run checks:

   ```bash
   pre-commit install --hook-type pre-commit
   pytest -v
   pre-commit run --all-files
   ```

5. Update docs if needed

### PR Template

PRs must follow the template in [`.github/PULL_REQUEST_TEMPLATE.md`](https://github.com/mcp-hangar/mcp-hangar/blob/main/.github/PULL_REQUEST_TEMPLATE.md). Required sections are enforced by the `pr-body / validate` CI check.

## Architecture Guidelines

**Value Objects:**

```python
mcp_server_id = McpServerId("my-mcp-server")  # Validated
```

**Events:**

```python
mcp_server.ensure_ready()
for event in mcp_server.collect_events():
    event_bus.publish(event)
```

**Exceptions:**

```python
# Basic usage
raise McpServerStartError(
    mcp_server_id="my-mcp-server",
    reason="Connection refused"
)

# With diagnostics (preferred)
raise McpServerStartError(
    mcp_server_id="my-mcp-server",
    reason="MCP initialization failed: process crashed",
    stderr="ModuleNotFoundError: No module named 'requests'",
    exit_code=1,
    suggestion="Install missing Python dependencies."
)

# Get user-friendly message
try:
    mcp_server.ensure_ready()
except McpServerStartError as e:
    print(e.get_user_message())
```

**Logging:**

```python
logger.info("mcp_server_started", mcp_server_id=mcp_server_id, mode=mode)
```

## Releasing

### Release Process Overview

MCP Hangar uses automated CI/CD for releases. The process ensures quality through:

1. **Version Validation** — Tag must match `pyproject.toml` version
2. **Full Test Suite** — All tests across Python 3.11-3.14
3. **Wheel smoke test** — the built wheel is installed and run, not the source tree
4. **Artifact Publishing** — PyPI package and Docker images

### Creating a Release

Releases are automated via [release-please](https://github.com/googleapis/release-please). When Conventional Commit PRs merge to `main`, release-please maintains a long-running Release PR that bumps the version, and the changelog is assembled onto it from `changelog.d/`. Merging that PR creates the version tag, which `release.yml` consumes to publish to PyPI and GHCR.

See [RELEASE.md](../runbooks/RELEASE.md) for the full operational runbook.

### Pre-release Versions

Pre-releases are published to **production PyPI**, not TestPyPI — TestPyPI was
dropped because its trusted publisher was never configured. They are cut by a
hand-pushed semver tag:

```bash
# Tag patterns for pre-releases
v2.0.0-alpha.1  # Alpha release
v2.0.0-beta.1   # Beta release
v2.0.0-rc.1     # Release candidate
```

Publishing to prod is safe because `pip` will not select a pre-release unless
asked. A pre-release carries no `latest` Docker tag and is marked as a
prerelease on GitHub (ADR-009).

Install a pre-release:

```bash
pip install --pre mcp-hangar            # newest pre-release
pip install "mcp-hangar==2.1.0rc1"      # an exact candidate
```

### Release Checklist

Before releasing, ensure:

- [ ] All tests pass locally: `pytest -v`
- [ ] Linting passes: `pre-commit run --all-files`
- [ ] Every non-trivial PR added its `changelog.d/` fragment (never edit CHANGELOG.md)
- [ ] Documentation is updated for new features
- [ ] Breaking changes have an upgrade note in `upgrade.d/`
- [ ] Version follows [Semantic Versioning](https://semver.org/)

### Versioning Guidelines

release-please computes the version from the Conventional Commit types:

| Change Type | Version Bump | Example |
| ------------- | -------------- | --------- |
| Bug fixes, patches | PATCH | 2.22.0 → 2.22.1 |
| New features (backward-compatible) | MINOR | 2.22.1 → 2.23.0 |
| Breaking changes | MINOR, with an upgrade note | 2.23.0 → 2.24.0 |

The 2.x line never computes a major: no commit uses `!` or `BREAKING CHANGE:`.
A major is a maintainer decision. See the
[deprecation policy](GIT_FLOW.md#deprecation-policy).

### Release Artifacts

Each release produces:

| Artifact | Location | Tags |
| ---------- | ---------- | ------ |
| Python Package | [PyPI](https://pypi.org/project/mcp-hangar/) | Version number |
| Docker Image | [GHCR](https://ghcr.io/mcp-hangar/mcp-hangar) | `latest`, `X.Y.Z`, `X.Y`, `X` |
| GitHub Release | Repository Releases | Changelog, install instructions |

### Hotfix Process

For urgent fixes on released versions, follow the [HOTFIX_RUNBOOK.md](HOTFIX_RUNBOOK.md).

## Licensing Model

MCP Hangar is licensed under the MIT License:

| Directory | License |
| ----------- | --------- |
| `src/mcp_hangar/` | MIT |
| `tests/`, `docs/`, `examples/` | MIT |

## Code of Conduct

Please read our [Code of Conduct](../code-of-conduct.md) before contributing.

## First Contribution?

Browse the [open issues](https://github.com/mcp-hangar/mcp-hangar/issues); the
repository has no `good first issue` label yet.

Questions? Open an [issue](https://github.com/mcp-hangar/mcp-hangar/issues/new);
GitHub Discussions are not enabled.
