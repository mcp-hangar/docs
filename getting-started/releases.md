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

On the 1.6.x line, now closed: 1.6.1 added the MCPEgressPolicy
Audit/Enforce mode on top of the 1.6.0 observability-hardening release, 1.6.2
caps the `mcp` SDK dependency below 2.x — without that cap a fresh install
follows the SDK into a major whose server surface this line does not use, and
the gateway dies at import — and 1.6.3 caps `httpx` below 1.0 for the same
reason on the same line.
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

## The 2.x line

The stable Python core is **2.0.0**, released 2026-07-31 — a plain `pip install
mcp-hangar` lands on it. It is built on the stable SDK (`mcp==2.0.0`) and speaks
the MCP 2026-07-28 protocol generation.

It is a major version. Read [Upgrade to 2.0.0](../upgrade.md) before you take
it: Slack approval delivery now needs an adapter you run yourself, and approval
resolution is authorized. Your upstream MCP servers do **not** have to move — a
connection that negotiates 2025-11-25 keeps working.

The **1.6.x line is closed**: no new features, and the approval-resolution
authorization fix is not backported. Pin `"mcp-hangar>=1.6,<2"` if you need to
stay there while you plan the upgrade.

1.6 added visibility through the front door — OTel-semconv traces and the L7
`MCPEgressPolicy` plane. 2.0 adds governance over task lifecycle
without executing it. It carries [ADR-014](../adr/ADR-014-tasks-relay-with-governance.md),
which lifts ADR-008's "relay-only, permanently" absolutism now that Tasks have
graduated out of `mcp.server.experimental` into a negotiated protocol extension
in the SDK v2 line.

**Landing in 2.0 — on the v2 preview, not on the 1.6.x line:**

- **Relay-with-governance, not execution.** Hangar relays upstream-created tasks
  and interposes governance on their lifecycle, engaging per-upstream on that
  upstream's first real task. It still does not create tasks, own a scheduler, or
  run a job-runner. It is not an executor.
- **Every relayed `task_id` is locally known.** On relaying an upstream
  `CreateTaskResult`, Hangar writes a `GovernedTaskStore` entry and emits
  `TaskCreated` before the handle reaches the client. The dead-handle failure
  mode is structurally excluded — rejection is replaced by a tracked record, not
  by pass-through.
- **Three serving handlers**, the SEP-2663 set: `tasks/get` (outcome inlined,
  pinned-digest verify before any payload is handed over), `tasks/update`,
  `tasks/cancel`. `tasks/result` and `tasks/list` are removed by the SEP and
  answer `-32601`.
- **On by default on the preview**, with `relay_tasks_enabled` retained as a
  per-deployment rollback. It was briefly off after the surface was found
  advertising a wire it did not serve; it went back on once that wire was served
  and verified ([ADR-015](../adr/ADR-015-vendored-task-wire.md)).
- **A governed mid-flight consent gate.** An upstream `input_required` surfaces
  its `inputRequests`; the client answers by driving `tasks/update`, and that
  update **is** the consent — gated before the answer reaches the upstream,
  consumed only on a confirmed relay, recorded as `TaskConsentDecided` (`#322`).
  Neither gate prompts a human: the L7 `requireApproval` gate **fails closed**,
  blocking a call pending an out-of-band decision, and this one fails closed on a
  decision the client volunteers. Hangar used to elicit the client itself; that
  belonged to the 2025-11-25 wire and is gone.

**Where the 2026-07-28 protocol stands on the rc.** All of it is served. The
stateless surface — `server/discover` (SEP-2575) and the `Mcp-Method` /
`Mcp-Name` header routing (SEP-2243) — is live on `serve --http`, and discover
reports the server's real capabilities and the caller's actual tool surface. The
**SEP-2663 Tasks reshape** is served too, from models vendored in Hangar rather
than taken from the SDK.

That last part was previously described here as forward-compat plumbing that
would self-activate when the SDK shipped the reshaped surface. It will not: the
SDK's `Task*` types are the SEP-1686 generation and shipped **unchanged in
`mcp==2.0.0`**, with the SEP-2663 extension still an open upstream PR. See
[ADR-015](../adr/ADR-015-vendored-task-wire.md). You can build against the
reshaped Tasks calls now.

Install it:

```bash
pip install mcp-hangar                # 2.0.0, the current stable release
pip install "mcp-hangar==2.0.0"       # pin it explicitly
```

Watch the [Releases page](https://github.com/mcp-hangar/mcp-hangar/releases) for
what lands next.

## Where to watch

- **All GHCR artifacts (image + charts):** <https://github.com/orgs/mcp-hangar/packages>
- **Releases:** the Releases page of each repository listed above.

[mcp-hangar/mcp-hangar]: https://github.com/mcp-hangar/mcp-hangar
[mcp-hangar/mcp-hangar-operator]: https://github.com/mcp-hangar/mcp-hangar-operator
[mcp-hangar/helm-charts]: https://github.com/mcp-hangar/helm-charts
[mcp-hangar/mcp-hangar#410]: https://github.com/mcp-hangar/mcp-hangar/issues/410
[PyPI]: https://pypi.org/project/mcp-hangar/
