# OpenTelemetry Integrations

Hangar is the **runtime governance layer** for MCP servers. It is not an observability
platform. Hangar exports governance telemetry -- enforcement decisions, MCP server
lifecycle events, capability violations, and identity-aware audit trails -- through
the OpenTelemetry (OTEL) interoperability contract. Partner backends visualize it.

```
Agent --> Hangar (governance) --> OTLP --> [OTEL Collector | OpenLIT | Langfuse | Grafana]
```

This page covers how to connect Hangar to each supported backend and what
governance data flows through.

---

## MCP Attribute Taxonomy

Every span, metric, and audit log emitted by Hangar carries MCP-specific attributes
defined in `src/mcp_hangar/observability/conventions.py`. These attributes form a
stable contract that partner backends consume without Hangar-specific plugins.

### MCP Server attributes

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.server.id` | string | Unique MCP server identifier (e.g. `math-server`) |
| `mcp.server.mode` | string | Operational mode: `subprocess`, `docker`, `remote` |
| `mcp.server.state` | string | Lifecycle state: `COLD`, `INITIALIZING`, `READY`, `DEGRADED`, `DEAD` |
| `mcp.server.group_id` | string | MCP Server group membership |
| `mcp.server.image` | string | Container image reference (docker mode) |
| `mcp.server.has_capabilities` | string | Whether MCP server declares capabilities (`true`/`false`) |
| `mcp.server.enforcement_mode` | string | Declared enforcement mode: `alert`, `block`, `quarantine` |

### Tool invocation attributes

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `gen_ai.tool.name` | string | Tool name as advertised by the MCP server |
| `mcp.tool.duration_ms` | float | Call duration in milliseconds |
| `mcp.tool.status` | string | Result: `success`, `error`, `timeout`, `blocked` |
| `mcp.tool.cold_start` | string | Whether this call triggered a cold start (`true`/`false`) |
| `mcp.tool.args_hash` | string | Argument hash for audit (raw arguments are never exported) |
| `mcp.tool.response_tokens` | int | Approximate token count of tool response |
| `mcp.session.id` | string | MCP protocol session identifier |
| `mcp.agent.id` | string | Agent or client identifier |
| `mcp.user.id` | string | Human user identity behind the agent request |
| `mcp.correlation_id` | string | Correlation ID for multi-step agent workflows |

### Enforcement attributes

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.enforcement.policy_result` | string | Policy evaluation result: `allow`, `deny`, `quarantine` |
| `mcp.enforcement.policy_name` | string | Name of the evaluated policy |
| `mcp.enforcement.action` | string | Action taken: `none`, `alert`, `block`, `quarantine`, `rate_limit` |
| `mcp.enforcement.violation_type` | string | Violation category: `egress_undeclared`, `tool_schema_drift`, `resource_limit_exceeded` |
| `mcp.enforcement.egress_destination` | string | Destination involved in egress violation (host:port) |
| `mcp.enforcement.violation_count` | int | Accumulated violations for this MCP server in this session |

### Audit attributes

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.audit.principal_type` | string | Principal type: `api_key`, `jwt`, `oidc`, `anonymous` |
| `mcp.audit.principal_id` | string | Principal identifier (API key ID, JWT sub claim) |
| `mcp.audit.principal_roles` | string | Roles held at call time (comma-separated) |
| `mcp.audit.authenticated` | string | Whether request passed authentication (`true`/`false`) |
| `mcp.audit.authorized` | string | Whether request passed authorization (`true`/`false`) |
| `mcp.audit.data_sensitivity` | string | Response classification: `public`, `internal`, `confidential`, `restricted` |

### Behavioral attributes

> **Roadmap / planned — not emitted in the current release.** These attributes
> are reserved for the behavioral/anomaly-detection path, which is held back.
> Deterministic enforcement does not populate them today; the table documents the
> reserved contract for a future release.

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.behavioral.matches_baseline` | string | Whether call matches baseline pattern (`true`/`false`) |
| `mcp.behavioral.anomaly_score` | float | Anomaly score (0.0 = normal, 1.0 = highly anomalous) |
| `mcp.behavioral.rule_id` | string | Detection rule that matched |
| `mcp.behavioral.pattern_step` | int | Sequence position in a detected multi-step pattern |
| `mcp.behavioral.pattern_name` | string | Name of the detected behavioral pattern |
| `mcp.behavioral.deviation_type` | string | Type of behavioral deviation detected |

### Caller attributes (identity propagation)

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.caller.type` | string | Caller type: `human`, `agent`, `service`, `anonymous` |
| `mcp.caller.id` | string | Caller identifier (user ID, service account, API key ID) |
| `mcp.caller.roles` | string | Roles held at invocation time (comma-separated) |

The identifiers in this taxonomy (`mcp.caller.id`, `mcp.user.id`, `mcp.agent.id`,
`mcp.session.id`) are off spans by default and need the opt-in described under
[Effective tracing configuration](#effective-tracing-configuration). Audit records
carry the caller regardless.

### Cost attributes (FinOps)

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.cost.cents` | int | Cost of invocation in hundredths of a cent |
| `mcp.cost.model` | string | Pricing model: `token`, `duration`, `fixed`, `composite` |
| `gen_ai.usage.input_tokens` | int | Input tokens consumed (LLM-backed tools) |
| `gen_ai.usage.output_tokens` | int | Output tokens produced (LLM-backed tools) |
| `mcp.cost.currency` | string | ISO 4217 currency code (default: `USD`) |

### Risk attributes (semantic analysis)

Attributes in the `mcp.risk.*` namespace carry detection rule match signals from the
semantic analysis engine. The engine evaluates multi-step tool call sequences per
agent session against detection rules (e.g. credential exfiltration, privilege
escalation). Partner backends such as OpenLIT, Grafana, and SIEM tools can filter
spans by `mcp.risk.severity = critical` to surface high-risk events.

`CapabilityViolationDetected` signals are emitted today (enforcement is
deterministic — rule- and threshold-based). `DetectionRuleMatched` is not: the
semantic analysis engine that would produce it is not shipped yet. The
`mcp.risk.score` and `mcp.risk.session_anomaly_score` attributes are reserved for the aggregate
behavioral anomaly-scoring path, which is **not yet enabled**: these session-level
scores are not populated in the current release.

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.risk.rule_id` | string | Matched detection rule identifier (e.g. `credential-exfiltration`) |
| `mcp.risk.pattern_name` | string | Human-readable name of the matched detection pattern |
| `mcp.risk.severity` | string | Severity: `critical`, `high`, `medium`, `low` |
| `mcp.risk.response_action` | string | Recommended response: `alert`, `throttle`, `suspend`, `block` |
| `mcp.risk.session_id` | string | Session ID where the match was detected |
| `mcp.risk.matched_tools` | string | Comma-separated tool names that formed the matched sequence |
| `mcp.risk.score` | float | Aggregate session risk score (0.0 = no risk, 1.0 = maximum risk) |
| `mcp.risk.session_anomaly_score` | float | Per-session anomaly score relative to baseline behavior |

### Health attributes

| Attribute | Type | Description |
| ----------- | ------ | ------------- |
| `mcp.health.result` | string | Health check result: `passed`, `failed`, `timeout` |
| `mcp.health.consecutive_failures` | int | Number of consecutive failures |
| `mcp.health.duration_ms` | float | Health check response time in milliseconds |

### Prometheus metric names

| Metric | Type | Description |
| -------- | ------ | ------------- |
| `mcp_hangar_tool_calls_total` | Counter | Total tool invocations |
| `mcp_hangar_tool_call_duration_seconds` | Histogram | Tool call latency distribution |
| `mcp_hangar_mcp_server_state` | Gauge | Current MCP server lifecycle state (0=cold, 1=initializing, 2=ready, 3=degraded, 4=dead) |
| `mcp_hangar_mcp_server_cold_start_seconds` | Histogram | Cold start duration (labels: `mcp_server`, `mode`) |
| `mcp_hangar_mcp_server_cold_start_in_progress` | Gauge | Cold starts currently in progress (labels: `mcp_server`) |
| `mcp_hangar_health_checks_total` | Counter | Total health checks |
| `mcp_hangar_circuit_breaker_state` | Gauge | Circuit breaker state per MCP server |
| `mcp_hangar_capability_violations_total` | Counter | Total capability violations |
| `mcp_hangar_cost_cents_total` | Counter | Total attributed cost in hundredths of a cent (labels: `mcp_server`, `tool`, `cost_model`) |
| `mcp_hangar_cost_attributions_total` | Counter | Total cost attribution computations (labels: `mcp_server`, `tool`) |

---

## OTEL Collector

The OTEL Collector is the recommended entry point for governance telemetry. It
receives OTLP from Hangar and routes spans, metrics, and logs to any supported
backend -- Prometheus, Jaeger, OpenLIT, Datadog, or a custom pipeline.

**Example:** [`examples/otel-collector/`](https://github.com/mcp-hangar/mcp-hangar/tree/main/examples/otel-collector)

### Getting started

Set these environment variables before starting Hangar:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=mcp-hangar
MCP_TRACING_ENABLED=true
```

Start the reference stack:

```bash
cd examples/otel-collector
docker-compose up
```

This starts:

| Service | Port | Purpose |
| --------- | ------ | --------- |
| Hangar | 8080 | MCP control plane with OTLP export |
| OTEL Collector | 4317 (gRPC), 4318 (HTTP) | Telemetry receiver and router |
| Prometheus | 9090 | Metrics storage and query |

The collector config (`otel-collector-config.yaml`) receives OTLP on both gRPC
and HTTP. It writes spans and audit records to stdout (the `debug` exporter) and
to a JSON-lines file (the `file` exporter). Hangar exports no OTLP metrics, and
Prometheus scrapes its `/metrics` endpoint directly. Replace the `debug` exporter
with your production backend.

### What flows through the collector

- **Traces:** one trace per request. The governance span `batch.call.<tool>`
  carries `mcp.server.id`, `gen_ai.tool.name`, the caller attributes the bound
  identity has, one `hangar.gate.decision` event per gate, and
  `hangar.call.outcome`. The upstream call is the CLIENT span `execute_tool <tool>`.
  The [tracing diagnosis runbook](../runbooks/tracing-diagnosis.md) shows the full
  span tree.
- **Logs:** audit records under scope `mcp_hangar.audit`, for tool invocations
  (`mcp.tool.status`, `mcp.tool.duration_ms`) and MCP server state transitions.
- **Metrics:** not sent over OTLP. Prometheus scrapes Hangar's `/metrics` endpoint.

### Effective tracing configuration

Hangar builds its tracer provider itself, so it resolves the standard variables
in its own code. For each setting, the first source that is set wins:

| Setting | Precedence |
| --- | --- |
| Protocol | `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL`, `OTEL_EXPORTER_OTLP_PROTOCOL`, then `grpc`. `http/protobuf` is the only other protocol accepted. Any other value adds no OTLP exporter and logs `tracing_otlp_exporter_unavailable`. |
| Endpoint | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `observability.tracing.otlp_endpoint` in `config.yaml`, then the SDK default: `http://localhost:4317` for gRPC, `http://localhost:4318/v1/traces` for HTTP. An empty `OTEL_EXPORTER_OTLP_ENDPOINT` adds no OTLP exporter. |
| TLS | `https://` always uses TLS. For gRPC, otherwise `OTEL_EXPORTER_OTLP_TRACES_INSECURE`, `OTEL_EXPORTER_OTLP_INSECURE`, then the scheme: `http://` is plaintext and an endpoint with no scheme uses TLS. For HTTP, the scheme alone decides. Headers such as `OTEL_EXPORTER_OTLP_HEADERS` are read by the SDK. |
| `service.name` | `OTEL_SERVICE_NAME`, `service.name` in `OTEL_RESOURCE_ATTRIBUTES`, `observability.tracing.service_name`, then `mcp-hangar`. |
| Resource | `OTEL_RESOURCE_ATTRIBUTES` wins for every key. `deployment.environment` falls back to `MCP_ENVIRONMENT`, then `development`. `service.instance.id` falls back to the instance id that Hangar also stamps on domain events. |
| Sampler | `OTEL_TRACES_SAMPLER`: `always_on`, `always_off`, `traceidratio`, `parentbased_always_on` (the default), `parentbased_always_off` or `parentbased_traceidratio`. Any other name logs `tracing_unknown_sampler` and uses the default. A ratio outside [0, 1] in `OTEL_TRACES_SAMPLER_ARG` logs `tracing_sampler_arg_invalid` and uses 1.0. |
| On or off | `MCP_TRACING_ENABLED`, then `observability.tracing.enabled`, default `true`. |
| Caller ids on spans | `MCP_TRACING_CALLER_IDS`, then `observability.tracing.caller_ids`, default `false`. Only when it is on does `batch.call.<tool>` carry `mcp.caller.id`, `mcp.user.id`, `mcp.agent.id` and `mcp.session.id`; caller type, tenant and correlation id are always there. On `main`, unreleased after 2.23.0; earlier releases set them unconditionally. |

Current limitations:

- Hangar does not read `OTEL_TRACES_EXPORTER` or `OTEL_PROPAGATORS`. It adds the
  OTLP exporter itself, and it propagates W3C `traceparent` and `tracestate` only,
  never baggage.
- Audit records are exported only when an endpoint is set explicitly, in
  `OTEL_EXPORTER_OTLP_ENDPOINT` or `observability.tracing.otlp_endpoint`. The
  signal-specific `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and
  `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` do not turn audit export on by themselves.
  `MCP_AUDIT_EXPORT_ENABLED=false` turns it off.
- No semantic-convention schema version is declared or pinned. The request-entry
  SERVER span, with `mcp.method.name`, `gen_ai.operation.name` and
  `gen_ai.tool.name`, is emitted by the pinned MCP SDK (`mcp==2.0.0`), not by
  Hangar.

**Supported versions.** The `mcp-hangar[opentelemetry]` extra requires
`opentelemetry-api`, `opentelemetry-sdk` and `opentelemetry-exporter-otlp` at
1.35.0 or later, the lowest release that installs beside the core dependencies.
The lockfile and CI test 1.44.0. The container image installs these packages
unpinned when it is built, so check the installed versions on a live install.

**Without a collector.** Tracing is on by default and exports to
`localhost:4317`. With nothing listening, export fails in the background and never
blocks a call, but every failed batch is logged and counted. Set
`MCP_TRACING_ENABLED=false` to turn Hangar's tracing off. To read spans locally
instead, set `MCP_TRACING_CONSOLE=true`, which adds an exporter that prints to
stderr, and set `OTEL_EXPORTER_OTLP_ENDPOINT` to an empty value so that no OTLP
exporter is added. Stderr is used because stdout carries the protocol on the
stdio transport.

### Tracer provider ownership

Hangar registers its own tracer provider only if no other provider was
registered first. If a host application or an instrumentation agent registered
one, including through `OTEL_PYTHON_TRACER_PROVIDER`, Hangar uses it and builds
nothing. It logs `tracing_external_provider_in_use`, and never replaces, flushes
or shuts that provider down. Hangar's sampler, length limits, resource, OTLP
exporter and `mcp_hangar_otlp_export_failures_total` counter then do not apply:
the owner's configuration does. `MCP_TRACING_ENABLED=false` still keeps Hangar's
spans out of a provider that someone else registered. Audit records follow the
same rule for the logger provider (`audit_log_external_provider_in_use`).

### Correlating logs and audit records with traces

- **Structured logs.** A line written inside a span carries `trace_id` and
  `span_id`. `batch_call_refused` is one such line, so a refusal found in the
  log leads to its trace.
- **OTLP audit records.** A record emitted inside a span carries that span's
  trace and span IDs, even when the span is not sampled. A record emitted
  outside any span, such as some server state changes, carries none. The core
  live test checks that the `tool_invocation` record arrives, but not that its
  trace ID matches the call's trace. Treat the audit-to-trace join as
  best-effort, not as guaranteed navigation.
- Both signals share the resource attributes `service.name` and
  `service.instance.id`, so a replica's records and spans can be matched.

---

## OpenLIT

OpenLIT provides a trace explorer, session analytics, and cost attribution UI.
Hangar exports governance telemetry; OpenLIT visualizes it. They connect through
the OTEL Collector -- Hangar does not send data directly to OpenLIT.

**Example:** [`examples/openlit/`](https://github.com/mcp-hangar/mcp-hangar/tree/main/examples/openlit)

### Getting started

```bash
cd examples/openlit
docker-compose up
```

This starts Hangar, an OTEL Collector, and OpenLIT. Open the OpenLIT dashboard at
<http://localhost:3000>.

Environment variables for Hangar (already set in the docker-compose):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=mcp-hangar
MCP_TRACING_ENABLED=true
```

### What governance data is visible in OpenLIT

In the OpenLIT trace explorer, filter on MCP governance attributes:

- **By MCP server:** `mcp.server.id = "math-server"`
- **By tool:** `gen_ai.tool.name = "add"`
- **By user:** `mcp.user.id = "alice"` (only with `MCP_TRACING_CALLER_IDS=true`)
- **By enforcement action:** `mcp.enforcement.action = "block"`
- **By violation type:** `mcp.enforcement.violation_type = "egress_undeclared"`

MCP Server lifecycle events (COLD, INITIALIZING, READY, DEGRADED, DEAD) appear as
audit log records with `mcp.server.state` attributes.

---

## Langfuse

Langfuse provides LLM-specific observability: input/output recording, token
counting, user session tracking, and evaluation workflows. It complements the
OTEL governance telemetry path -- Langfuse handles LLM observability while OTEL
handles governance observability.

- **OTEL path:** Enforcement decisions, capability violations, MCP server lifecycle,
  audit trails. Exported via OTLP to any OTEL-compatible backend.
- **Langfuse path:** Tool call input/output, token counts, user session traces.
  Exported via the `LangfuseObservabilityAdapter`.

**Example:** [`examples/langfuse/`](https://github.com/mcp-hangar/mcp-hangar/tree/main/examples/langfuse)

### Getting started

You need a running Langfuse instance -- either [Langfuse Cloud](https://cloud.langfuse.com/)
or a self-hosted deployment.

Set these environment variables:

```bash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
```

Enable Langfuse in `config.yaml`:

```yaml
observability:
  langfuse:
    enabled: true
    # Keys are read from environment variables
    # Never put secret keys in config files
```

!!! warning "Secret handling"
    `LANGFUSE_SECRET_KEY` is a secret. Use environment variables, HashiCorp Vault,
    or Kubernetes secrets. Never commit secrets to config files or source control.

### How Hangar maps to Langfuse concepts

| Langfuse concept | Hangar mapping |
| ------------------ | ---------------- |
| Trace | One MCP session (`mcp.session.id`) |
| Span | MCP Server tool invocation |
| Generation | Tool call with input/output |
| User | `mcp.user.id` from identity propagation |

When Hangar propagates caller identity, Langfuse traces carry the same `user_id`
and `session_id` as the MCP OTEL spans. This enables cross-referencing Langfuse
traces with governance enforcement events in OTEL backends.

---

## Grafana

Hangar exposes Prometheus metrics at the `/metrics` HTTP endpoint. Grafana can
scrape these directly or consume them through the OTEL Collector's Prometheus
exporter.

Four maintained Grafana dashboards ship with the [`mcp-hangar` Helm
chart](https://github.com/mcp-hangar/helm-charts), source in
[`mcp-hangar/files/dashboards/`](https://github.com/mcp-hangar/helm-charts/tree/main/mcp-hangar/files/dashboards):

- **Overview dashboard:** MCP server states, tool call rates, error rates
- **Provider details dashboard:** Per-MCP server metrics, health check history
- **Alerts dashboard:** Circuit breaker state, violation counts
- **Governance dashboard:** Cost attribution, policy violations, enforcement actions

### Getting started

Prometheus and Grafana are yours to run — Hangar ships no stack. On Kubernetes,
`dashboards.enabled=true` renders the four as ConfigMaps for the Grafana
sidecar to auto-import; elsewhere, import the JSON by hand from the link above.

Start Hangar in HTTP mode so the `/metrics` endpoint is available:

```bash
mcp-hangar serve --http --port 8000
```

### Key Prometheus queries

```promql
# Tool call rate per mcp_server (last 5 minutes)
rate(mcp_hangar_tool_calls_total[5m])

# 95th percentile tool call latency
histogram_quantile(0.95, rate(mcp_hangar_tool_call_duration_seconds_bucket[5m]))

# MCP servers currently in DEGRADED state (3=degraded)
mcp_hangar_mcp_server_state == 3

# Circuit breaker open count
mcp_hangar_circuit_breaker_state == 1
```

---

## Integration stance

Hangar is not trying to become an observability platform. OpenTelemetry-compatible
tools -- OpenLIT, Langfuse, Grafana, OTEL Collector, Datadog, Honeycomb -- are
**extensions to the visibility layer** around Hangar. Hangar defines the governance
telemetry contract (the MCP attribute taxonomy above) and exports it via OTEL.
Partner tools consume, correlate, alert, and visualize.

This separation means:

- Hangar focuses on runtime security enforcement, lifecycle management, and
  governance policy.
- Partner tools focus on visualization, alerting, session analytics, and cost
  attribution.
- The OTEL interoperability contract ensures any OTEL-compatible tool works
  without Hangar-specific plugins.
