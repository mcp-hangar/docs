# Releases & Artifacts

MCP Hangar ships as three independently versioned artifacts, each in its own
repository. This page is the single index of where each one lives and how to
install it.

> **Note**
> Publishing for the operator image and the Helm charts is being rolled out per
> the release-topology decision ([mcp-hangar/mcp-hangar#410]). Until the first
> release of each lands, install the Python core from PyPI.

## At a glance

| Artifact | Source repo | Registry / index | Install |
| --- | --- | --- | --- |
| Python core (`mcp-hangar`) | [mcp-hangar/mcp-hangar] | [PyPI] | `pip install mcp-hangar` |
| Operator image | [mcp-hangar/mcp-hangar-operator] | GHCR: `ghcr.io/mcp-hangar/mcp-hangar-operator` | `kubectl apply -f …/install.yaml` |
| Helm charts | [mcp-hangar/helm-charts] | GHCR OCI: `oci://ghcr.io/mcp-hangar/charts` | `helm install … oci://…` |

## Python core (PyPI)

```bash
pip install mcp-hangar
```

- Package: <https://pypi.org/project/mcp-hangar/>
- Releases & changelog: <https://github.com/mcp-hangar/mcp-hangar/releases>

## Operator (container image + install manifest)

The operator publishes a multi-arch (`linux/amd64`, `linux/arm64`) image and a
rendered install manifest on every `vX.Y.Z` tag.

Image reference:

```text
ghcr.io/mcp-hangar/mcp-hangar-operator:<version>
```

Install the rendered manifest straight from a release:

```bash
kubectl apply -f https://github.com/mcp-hangar/mcp-hangar-operator/releases/latest/download/install.yaml
```

- Source & releases: <https://github.com/mcp-hangar/mcp-hangar-operator/releases>

## Helm charts (OCI)

Two charts are published to the GHCR OCI registry — no `helm repo add` needed:

| Chart | Purpose |
| --- | --- |
| `mcp-hangar` | Core gateway |
| `mcp-hangar-operator` | Kubernetes operator |

Install a chart (pin a version):

```bash
helm install mcp-hangar \
  oci://ghcr.io/mcp-hangar/charts/mcp-hangar --version <version>

helm install mcp-hangar-operator \
  oci://ghcr.io/mcp-hangar/charts/mcp-hangar-operator --version <version>
```

Inspect a chart before installing:

```bash
helm show chart oci://ghcr.io/mcp-hangar/charts/mcp-hangar
```

- Source: <https://github.com/mcp-hangar/helm-charts>

## Versioning

Each artifact follows SemVer and versions **independently** — the Python core,
the operator image, and the charts do not share a version line. Check each
repo's Releases page and changelog for its current version.

## Upgrade notes

Per-release, user-visible migration steps live in the [Upgrade Guide](../upgrade.md).

### 1.6.0 — breaking for trace/metrics consumers

The current stable Python core is **1.6.0**, an observability-hardening release.
It contains a **silent breaking change for telemetry consumers**: tool-invocation
spans were renamed to the OpenTelemetry GenAI/MCP semantic conventions, so any
dashboard, saved query, or alert keyed on the **old** span/attribute names keeps
running but matches nothing after upgrade. The renames include:

- `mcp.tool.name` → `gen_ai.tool.name`
- `mcp.cost.input_tokens` → `gen_ai.usage.input_tokens`
- `mcp.cost.output_tokens` → `gen_ai.usage.output_tokens`
- span name `tool.invoke.{tool}` → `execute_tool {tool}`

Three never-emitted HTTP/SSE metrics were also removed. Audit your Grafana/PromQL
and OTLP audit queries **before** upgrading. See
[Upgrade to 1.6.0](../upgrade.md#upgrade-to-160) for the full attribute mapping
and the new transport message metrics, and the
[Egress Policy guide](../guides/EGRESS_POLICY.md) for the L7 `MCPEgressPolicy`
enforcement plane that also ships in this release.

## Where to watch

- **All GHCR artifacts (image + charts):** <https://github.com/orgs/mcp-hangar/packages>
- **Releases:** the Releases page of each repository listed above.

[mcp-hangar/mcp-hangar]: https://github.com/mcp-hangar/mcp-hangar
[mcp-hangar/mcp-hangar-operator]: https://github.com/mcp-hangar/mcp-hangar-operator
[mcp-hangar/helm-charts]: https://github.com/mcp-hangar/helm-charts
[mcp-hangar/mcp-hangar#410]: https://github.com/mcp-hangar/mcp-hangar/issues/410
[PyPI]: https://pypi.org/project/mcp-hangar/
