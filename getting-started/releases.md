# Releases & Artifacts

MCP Hangar ships as three independently versioned artifacts, each in its own
repository. This page is the single index of where each one lives and how to
install it.

> **Note**
> Each artifact is released independently per the release-topology decision
> ([mcp-hangar/mcp-hangar#410]): the Python core on PyPI, the operator image and
> `install.yaml` on GHCR / GitHub Releases (operator `v0.14.0`), and the Helm
> charts as OCI packages. Each advances on its own cadence.

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
engine armed in this release. Note the version requirement: the core policy
engine and REST intake ship in 1.6.0, and end-to-end enforcement also needs the
operator's `MCPEgressPolicy` controller, which ships in operator **v0.14.0**.
Run **core 1.6.0+** and **operator v0.14.0+** for end-to-end L7 — both are
released.

## v2 preview (prerelease)

The stable Python core is **1.6.0** and stays that way — a plain `pip install
mcp-hangar` lands on 1.6.0, and nothing below changes that. The **v2 line is a
prerelease**: `mcp-hangar==2.0.0a1`, built on the SDK v2 beta (`mcp==2.0.0b2`).
It is opt-in only. You will not get it by accident.

1.6 added visibility through the front door — OTel-semconv traces and the L7
`MCPEgressPolicy` plane. The v2 preview adds governance over task lifecycle
without executing it. It carries [ADR-014](../adr/ADR-014-tasks-relay-with-governance.md),
which lifts ADR-008's "relay-only, permanently" absolutism now that Tasks have
graduated out of `mcp.server.experimental` into a negotiated protocol extension
in `mcp==2.0.0b2`.

**Landing in 2.0 — on the v2 preview, not in 1.6.0:**

- **Relay-with-governance, not execution.** Hangar relays upstream-created tasks
  and interposes governance on their lifecycle, engaging per-upstream on that
  upstream's first real task. It still does not create tasks, own a scheduler, or
  run a job-runner. It is not an executor.
- **Every relayed `task_id` is locally known.** On relaying an upstream
  `CreateTaskResult`, Hangar writes a `GovernedTaskStore` entry and emits
  `TaskCreated` before the handle reaches the client. The dead-handle failure
  mode is structurally excluded — rejection is replaced by a tracked record, not
  by pass-through.
- **Four serving handlers:** `tasks/get`, `tasks/result` (pinned-digest
  verify), `tasks/cancel`, and owner-only `tasks/list`.
- **One genuinely interactive consent gate.** The mid-flight `input_required`
  path (`#322`) routes to real human-in-the-loop elicitation and is recorded as
  `TaskConsentDecided`. It is the only interactive consent flow in the stack. The
  L7 `requireApproval` gate is a different shape entirely: it **fails closed**,
  blocking a gated call pending an out-of-band decision — it is **not** an
  interactive approval queue.

Still **coming, not shipped:** the 2026-07-28 protocol handshake and the
SEP-2663 Tasks reshape are forward-compat only. Do not build against them yet.

Get the preview:

```bash
pip install --pre mcp-hangar          # newest prerelease on the v2 line
pip install "mcp-hangar==2.0.0a1"     # pin the exact prerelease
```

Watch the [Releases page](https://github.com/mcp-hangar/mcp-hangar/releases) for
the a-line to move. Until 2.0 is cut, `pip install mcp-hangar` remains 1.6.0.

## Where to watch

- **All GHCR artifacts (image + charts):** <https://github.com/orgs/mcp-hangar/packages>
- **Releases:** the Releases page of each repository listed above.

[mcp-hangar/mcp-hangar]: https://github.com/mcp-hangar/mcp-hangar
[mcp-hangar/mcp-hangar-operator]: https://github.com/mcp-hangar/mcp-hangar-operator
[mcp-hangar/helm-charts]: https://github.com/mcp-hangar/helm-charts
[mcp-hangar/mcp-hangar#410]: https://github.com/mcp-hangar/mcp-hangar/issues/410
[PyPI]: https://pypi.org/project/mcp-hangar/
