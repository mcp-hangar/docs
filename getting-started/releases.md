# Releases & Artifacts

MCP Hangar ships as three independently versioned artifacts, each in its own
repository. This page is the single index of where each one lives and how to
install it.

> **Note**
> Each artifact is released independently per the release-topology decision
> ([mcp-hangar/mcp-hangar#410]): the Python core on PyPI, the operator image and
> `install.yaml` on GHCR / GitHub Releases, and the Helm charts as OCI
> packages. Each advances on its own cadence, so there is no single
> "MCP Hangar version" — the current pairing lives in the
> [compatibility matrix](../operations/RELEASE_COMPATIBILITY.md), which is
> regenerated from the registry rather than maintained by hand.

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

The stable Python core is **2.6.0**, released 2026-08-11 — a plain `pip install
mcp-hangar` lands on it. It is built on the stable SDK (`mcp==2.0.0`) and speaks
the MCP 2026-07-28 protocol generation.

**2.6.0 makes governance that was advertised actually run.** Three enforcement
surfaces were declared and did nothing. Digest pins could only be addressed to a
tenant, and the tenant comes from the authenticated principal — so on a gateway
without authentication no pin was ever matched, while `initialize` went on
advertising the capability with all three enforcement modes. Twenty-one of the
twenty-two `hangar_*` tools authorized nothing at all, so any valid credential
could stop a server or reload the configuration over MCP while the REST API
refused the same identity. And a `remote` upstream declared in `config.yaml` sat
outside the SSRF policy without saying so.

Pins can now be declared for every caller, the `hangar_*` tools require the
permission their REST equivalent has always required, and a config-file upstream
outside the policy names itself at startup. A `front_door` gateway also shows an
operator the management tools its role permits, so one deployment can serve an
agent without a control plane and an operator with one.

**Two of these can stop a gateway that works today** — a configuration with
per-tenant pins and authentication off no longer boots, and an API key that drove
the fleet over MCP now needs the role it always needed over REST. Read
[Upgrade to 2.6.0](../upgrade.md#upgrade-to-260) before rolling out.

**2.5.3 made the gateway stop saying things that are not true**, which is what
the six fixes in it have in common. It advertised `prompts` and `resources` and
served neither, so a client reading `{"prompts": []}` concluded the upstream had
none; both capabilities are now withdrawn and those methods answer `-32601`. It
never finished the MCP handshake, so an upstream that registers tools on
initialization had them silently missing from the catalogue — that handshake is
finished now, and such a catalogue **grows** on upgrade. It introduced itself to
every upstream as `mcp-registry / 1.0.0`, a product name that has not existed
for a long time. It discarded a tool's `title`, `annotations`, `execution`,
`icons` and `_meta`, so `readOnlyHint` and `destructiveHint` — how a client
decides whether a call needs a human in front of it — never reached anyone.
And a `front_door` serving zero tools was silent about which of three very
different reasons produced that. Tool digests are unchanged, so no pin moves.
See [Upgrade to 2.5.3](../upgrade.md#upgrade-to-253).

**2.5.2 is the release to be on if you select a storage backend.** On 2.5.0 and
2.5.1, `persistence.backend` handed the auth stores out without creating their
tables, so an auth-enabled gateway died at startup on `relation "roles" does not
exist` — or, with no `role_assignments` configured to trip that, on
`tool_access_policies`. Both backends were affected; SQLite failed the same way
with `no such table: roles`. That is the configuration more than one replica
requires, so the documented multi-replica deployment could not start. The same
release makes `auth bootstrap-admin` work on that configuration (it consulted
only `auth.storage.driver`, whose default is not durable, and refused), lets the
`provider-admin` role deliver an egress policy instead of answering 403, applies
`MCP_TRUSTED_HOSTS` to the MCP endpoint rather than the REST API alone, and
gives `tool_access.mode: front_door` back its per-tenant tool list. See
[Upgrade to 2.5.2](../upgrade.md#upgrade-to-252).

**2.5.1 is a patch worth applying rather than noting.** The connect-time SSRF
re-check that 2.5.0 advertised was not written to a server's stored record, so
it was lost on every restart and never ran on a replica that learned of the
registration from the shared log. 2.5.1 restores it, including for servers
registered while 2.5.0 was running — upgrade and restart, no re-registration
needed. It also refuses a `coordination:` block that names no
`persistence.backend` at all, which used to boot into the fleet-per-pod failure
the block exists to prevent. See [Upgrade to 2.5.1](../upgrade.md#upgrade-to-251).

**2.5.0 makes storage one decision and lets a deployment run more than one
replica.** `persistence.backend: sqlite | postgresql` picks one backend for
every persisted concern, and a backend that does not serve all of them is
refused rather than half-applied. A `coordination:` block is the statement that
several replicas are one gateway: exactly one instance holds the management
lease, PostgreSQL is required — replicas that cannot share storage are not a
cluster, so a file-backed backend refuses to start — and a server declared there
has to be in `remote` mode, because `subprocess`, `docker` and `container`
attach a child process's stdio to a single replica. *Registering* one of those
modes through the API is refused on a different axis: whenever the storage can
be shared, which a single gateway on PostgreSQL already is, with or without a
`coordination:` block. It also ships discovery source management as Preview —
nothing is gated on a header, but every mutating response carries
`X-Hangar-Preview: discovery-source-management` so a client can detect the
preview status — and re-checks SSRF policy at connect time rather than only at
registration, a check 2.5.0 lost on restart and 2.5.1 restores (see
[hardening a public gateway](../cookbook/23-harden-public-gateway.md#threat-model)).
See [Upgrade to 2.5.0](../upgrade.md#upgrade-to-250) and
[Running more than one replica](../cookbook/25-multiple-replicas.md).

**2.1.0 makes the human-in-the-loop approval gate reachable — for the first
time.** The control was documented, unit-tested and wired nowhere: no
configuration key could put a tool behind it, the gate service was never
constructed on a shipped path, and `GET /api/approvals` answered `500` while a
call the policy said to hold executed immediately
([#678](https://github.com/mcp-hangar/mcp-hangar/issues/678)). A `tools:` block
now accepts `approval_list`, `approval_timeout_seconds` and `approval_channel`
everywhere it already accepted `allow_list`/`deny_list`, the gate service is
built independently of auth, and the REST surface reads the same service the
enforcement path does. Nothing that worked before behaves differently — hence a
minor rather than a patch. See
[Tool access control](../reference/configuration.md#tools-dual-format) for the
keys and [Upgrade to 2.1.0](../upgrade.md#upgrade-to-210) for the one thing that
can bite.

It also adds a **startup reachability check**: if the configuration demands a
subsystem this process cannot reach — a tool on `approval_list` with no gate
service, say — the server refuses to boot instead of starting clean and doing
less than its configuration said. `startup_checks: {enforce: false}` downgrades
the refusals to error logs; there is deliberately no switch that silences them.

2.0.1 was a security patch on top of 2.0.0 and is drop-in: the approval gate
re-establishes an approval's validity at dispatch rather than only at decision,
so a call whose world moved while its approval was held is refused where it
previously executed ([#674](https://github.com/mcp-hangar/mcp-hangar/issues/674)).
See [Upgrade to 2.0.1](../upgrade.md#upgrade-to-201).

The 2.0.0 notes below still apply — it is a major version. Read
[Upgrade to 2.0.0](../upgrade.md) before you take
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

**What the governed task relay gives you, from 2.0.0:**

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
  Neither of these gates prompts a human: the L7 `requireApproval` gate **fails
  closed**, blocking a call pending an out-of-band decision, and this one fails
  closed on a decision the client volunteers. Hangar used to elicit the client
  itself; that belonged to the 2025-11-25 wire and is gone. The gate that *does*
  hold a call for a human is the separate tool-access
  [`approval_list`](../reference/configuration.md#holding-a-tool-for-a-human-approval_list),
  reachable from 2.1.0.

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
pip install mcp-hangar                # 2.5.1, the current stable release
pip install "mcp-hangar==2.5.1"       # pin it explicitly
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
