# Testing

## Quick Start

```bash
uv sync --extra dev
uv run pytest tests/unit
```

The unit tier is the one you run while working — roughly 6,600 tests in about
half a minute. `pytest` with no path runs everything under `tests/`, which adds
the integration tier and the in-process conformance and CI-metadata checks.

## Running Tests

```bash
# The tier you edit against
pytest tests/unit

# One file, or one test
pytest tests/unit/test_registry_cache.py
pytest tests/unit/test_registry_cache.py::TestRegistryCache::test_set_and_get

# Everything CI runs on a PR
pytest --ignore=tests/integration
pytest tests/integration/

# Coverage, when you actually want it
pytest tests/unit tests/integration --cov=mcp_hangar --cov-report=term-missing
```

Coverage is not on by default. It costs about 18 seconds and 6,600 lines of
output on every run, including a run of a single file, so the jobs that read a
report ask for it explicitly.

### Markers

| Marker | Description |
| -------- | ------------- |
| `benchmark` | Performance benchmarks (pytest-benchmark) |
| `security` | Security regression tests — the category is the marker, not a directory |
| `live` | Black-box verification against a running gateway; opt-in |
| `t0` | Live tier 0 — single process, stub backend |
| `t1` | Live tier 1 — multi-backend / groups, needs compose |
| `t2` | Live tier 2 — auth / IdP, needs Keycloak |

That is the whole list, and all six are registered in `pyproject.toml`.
`pytest` does not run with `--strict-markers`, so `-m something-else` selects
nothing and exits green — a passing run of zero tests. Check the collected
count when a marker filter returns suspiciously fast.

### There are no opt-in flags

A test that only runs behind a flag nobody passes does not run. `--run-containers`
and `--run-slow`, the testcontainers fixtures behind them, and the `containers`
pip extra were all deleted for that reason: the tiers had been dead for months
and nothing noticed. Anything that needs a real runtime belongs in `tests/live`
(nightly) or in a lab you drive by hand.

## Test Tiers

| Path | What it is | How it runs |
| ------ | ----------- | ------------- |
| `tests/unit/` | The bulk of the suite, in-process | every PR |
| `tests/integration/` | Multiple components together, still in-process | every PR, its own job |
| `tests/conformance/` | The gateway against the MCP spec | every PR |
| `tests/ci/` | Assertions about the repo's own workflows | every PR |
| `tests/benchmark/` | pytest-benchmark timings | every PR (collected by the bare `pytest` run) |
| `tests/live/` | Black-box against a running gateway | nightly, opt-in |
| `tests/acceptance/` | A shell script against a cluster you own | by hand |

### Live verification

`tests/live` is gated on an environment variable, not a flag, and skips
entirely without it:

```bash
MCP_HANGAR_LIVE_VERIFY=1 pytest tests/live -m t0 --timeout=180 -ra
```

Tier `t0` needs only a running gateway. `t1` needs a compose stack, `t2` needs
Keycloak. See `tests/live/README.md` in the core repo for what each tier
assumes.

### Acceptance

`tests/acceptance/ha_two_gateways.sh` is a shell script, run by hand against a
cluster you own — it kills a pod. It is deliberately not pytest: it tests the
deployment, which is how it found that a shipped image carried no PostgreSQL
driver. Apply the manifests beside it (`ha-postgres.yaml`, `ha-gateway.yaml`)
first.

## Property-Based Testing

MCP Hangar uses [Hypothesis](https://hypothesis.readthedocs.io/) for
property-based testing.

```bash
pytest tests/unit/observability/test_property_based.py -v

# Reproduce a specific run
pytest tests/unit/observability/test_property_based.py --hypothesis-seed=12345
```

### Example Property Test

```python
from hypothesis import given, strategies as st

@given(
    mcp_server_name=st.text(min_size=1, max_size=50),
    tool_name=st.text(min_size=1, max_size=50),
)
def test_adapter_accepts_any_strings(mcp_server_name, tool_name):
    """Adapter accepts any valid string inputs."""
    adapter = NullObservabilityAdapter()
    span = adapter.start_tool_span(mcp_server_name, tool_name, {})
    assert isinstance(span, NullSpanHandle)
```

## Manual Testing

### Mock MCP server

`tests/mock_provider.py` implements the JSON-RPC MCP protocol and is what the
suite points a subprocess MCP server at:

```yaml
# config.yaml
mcp_servers:
  math:
    mode: subprocess
    command: [python, tests/mock_provider.py]
```

```bash
mcp-hangar serve --http
```

Drive it directly to check a handshake:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python tests/mock_provider.py
```

### Test via Python

```python
from mcp_hangar.domain.model import McpServer

mcp_server = McpServer(
    mcp_server_id="test",
    mode="subprocess",
    command=["python", "tests/mock_provider.py"]
)

mcp_server.ensure_ready()

result = mcp_server.invoke_tool("add", {"a": 5, "b": 3})
print(result)  # {"result": 8}

mcp_server.shutdown()
```

## Common Issues

### MCP server won't start

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python tests/mock_provider.py
```

### Permission denied (container)

```yaml
mcp_servers:
  memory:
    mode: container
    read_only: false
    volumes:
      - "./data:/app/data:rw"
```

### Tests hang

```bash
pytest tests/ -v --timeout=60
```
