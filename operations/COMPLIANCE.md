# Compliance Export

Hangar can forward audit events to a SIEM or log aggregator in a structured
format. Four formats are supported: CEF, LEEF 2.0, JSON-lines, and RFC 5424
syslog.

> For how these exports and the rest of Hangar's controls map to the __EU AI Act
> and SOC 2__ — and, importantly, what Hangar does _not_ claim — see
> [Compliance Posture](./COMPLIANCE_POSTURE.md).

## Configuration

Two environment variables control the compliance pipeline:

| Variable | Required | Default | Description |
| ---------- | ---------- | --------- | ------------- |
| `MCP_COMPLIANCE_FORMAT` | Yes | _(unset)_ | Format to use: `cef`, `leef`, `jsonlines`, `json-lines`, `syslog`. Case-insensitive; since 2.25.0 surrounding whitespace is trimmed. Any other value refuses startup. |
| `MCP_COMPLIANCE_OUTPUT` | No | stderr | File path to write output. When unset, lines go to stderr for container log collection. Since 2.25.0 a path that cannot be appended to refuses startup. |

When `MCP_COMPLIANCE_FORMAT` is set, Hangar registers a second audit event
handler that forwards `ToolInvocationCompleted`, `ToolInvocationFailed`,
`ToolCallRefused`, and `McpServerStateChanged` events to the chosen exporter.
This handler runs independently of the OTLP audit exporter. The records are
typed `ToolInvocationCompleted`, `ToolInvocationFailed`, `ToolInvocationDenied`
(a call a gate refused before it reached the upstream: tool access, approval,
digest pin, L7), and `ProviderStateChanged`.

Compliance exporters ship in the main `mcp_hangar` package; no separate module
or license key is required.

### Delivery failures

_Since 2.25.0_ an export the gateway cannot perform refuses startup with a
`ConfigurationError` naming the value
([mcp-hangar#1701](https://github.com/mcp-hangar/mcp-hangar/issues/1701)):

```text
Unknown MCP_COMPLIANCE_FORMAT 'cefx'; expected one of: cef, json-lines, jsonlines, leef, syslog
MCP_COMPLIANCE_OUTPUT '/var/log/hangar/audit.cef' cannot be appended to: [Errno 2] No such file or directory: ...
```

So does a set `MCP_COMPLIANCE_FORMAT` whose exporter cannot be imported. Fix
the format, create the output directory writable by the gateway's user, or
unset `MCP_COMPLIANCE_OUTPUT` to export to stderr. To run with no SIEM export,
unset `MCP_COMPLIANCE_FORMAT`.

A write that fails after startup -- the directory removed, the disk full -- does
not stop the gateway or refuse calls. The record is dropped and:

- counted in `mcp_hangar_compliance_export_failures_total`, labelled `format`
  (`cef`, `leef`, `jsonlines`, `syslog`) and `reason` (`not_found`,
  `permission_denied`, `is_a_directory`, `no_space`, `os_error`);
- logged once per burst: `compliance_export_write_failed` at error on the
  first failure, `compliance_export_write_recovered` with the number `dropped`
  when a write succeeds again;
- reported in a `compliance_export` field, `status: degraded`, on
  `/health/ready` (without the file path, and still `200`) and on
  [`hangar_health`](../reference/tools.md#hangar_health) (with the path, and
  the tool's own `status` turns `degraded`).

Alert on the counter: readiness does not drain a replica whose SIEM feed is
broken, by design.

__Before 2.25.0 the feed did not fail closed.__ An unrecognised
`MCP_COMPLIANCE_FORMAT` logged `unknown_compliance_format` at warning, an
exporter that could not be imported logged `compliance_exporter_unavailable`,
and the gateway started with no compliance export at all. A record the exporter
could not write was logged at error and dropped, with no metric. An export
from such a gateway can be missing records without saying so.

A successful start logs `compliance_exporter_registered` with the format and
output.

## Format reference

The examples below are records written by core 2.24.0 for a call to `add` on a
server named `math` by an API-key principal `user:developer`.

### CEF (Common Event Format)

```text
CEF:0|MCP Hangar|MCP Hangar|0.15.0|101|Tool Invocation Completed|1|rt=1791142564436 dvchost=mcp-hangar act=ToolInvocationCompleted cs1=math cs1Label=ProviderID suser=user:developer spriv=developer flexString1=math flexString1Label=RouteBackend cs5=add cs5Label=ToolName cn1=0.34 cn1Label=DurationMs
```

Signature IDs: `101` completed, `102` failed, `103` denied, `202` state change.
The device-version field is a fixed `0.15.0`, not the running release. A CEF
state-change record names the server (`cs1`) but not the old and new state;
the other three formats carry both.

Compatible with ArcSight, Splunk, QRadar, and any CEF-aware SIEM.

### LEEF 2.0 (IBM QRadar)

```text
LEEF:2.0|MCP Hangar|MCP Hangar|0.15.0|101|\tdevTime=Oct 04 2026 19:38:29\tproto=tool\tusrName=user:developer\trole=developer\taction=add\tduration=0.31\tsrc=math\trouteBackend=math
```

Tab-delimited extensions following the LEEF 2.0 specification (`\t` above
stands for a tab). Event IDs match the CEF signature IDs.

### JSON-lines

```json
{"timestamp": "2026-10-04T19:38:33.384109+00:00", "event_type": "ToolInvocationCompleted", "provider_id": "math", "route_backend": "math", "tool_name": "add", "status": "success", "duration_ms": 0.31, "user_id": "user:developer", "caller_roles": "developer"}
```

One JSON object per line; a field with no value is left out. Fields are listed
under [Exported fields](#exported-fields).

### RFC 5424 syslog

```text
<134>1 2026-10-04T19:38:37.282099Z gateway-host mcp-hangar 92463 101 [mcp@49152 provider="math" routeBackend="math" tool="add" status="success" duration="0.46" user="user:developer" roles="developer"] Tool add on provider math success
```

Facility `local0`; severity informational for a completed call, error for a
failed one, warning for a refusal or a state change. HOSTNAME is the gateway's
host name, PROCID its process id, and MSGID the CEF signature ID. Suitable for
rsyslog, syslog-ng, and Fluentd syslog inputs.

## Examples

`serve --http` binds `0.0.0.0` by default, which refuses to start without
authentication; the examples bind loopback for a local run with auth off.
Create the output directory first (see [Delivery failures](#delivery-failures)).

Start Hangar with CEF output to a file:

```bash
MCP_COMPLIANCE_FORMAT=cef MCP_COMPLIANCE_OUTPUT=/var/log/mcp-hangar/cef.log \
  mcp-hangar serve --http --host 127.0.0.1 --port 8000 --config config.yaml
```

JSON-lines to stderr (for Docker log drivers):

```bash
MCP_COMPLIANCE_FORMAT=jsonlines mcp-hangar serve --http --host 127.0.0.1 --port 8000 --config config.yaml
```

## Exported fields

What each format writes for a tool-call record, by key. A field with no value is
omitted.

| Field | JSON-lines | CEF | LEEF | syslog |
| ------- | -------- | ------- | ------- | ------- |
| MCP server the caller named | `provider_id` | `cs1` | `src` | `provider` |
| Server the call was routed to (a group's member) | `route_backend` | `flexString1` | `routeBackend` | `routeBackend` |
| Tool name | `tool_name` | `cs5` | `action` | `tool` |
| Outcome: `success`, `error`, `denied` | `status` | `act` (event type) | event ID | `status` |
| Call duration (ms) | `duration_ms` | `cn1` | `duration` | `duration` |
| Caller principal | `user_id` | `suser` | `usrName` | `user` |
| Role that authorized the call | `caller_roles` | `spriv` | `role` | `roles` |
| Session | `session_id` | `cs3` | `sessID` | `session` |
| Tenant | `tenant_id` | `cs6` | `tenantID` | `tenant` |
| Upstream error (the upstream JSON-RPC error code, e.g. `-1`) | `error_type` | `reason` | `reason` | `error` |
| Refusing gate and its reason code | `gate`, `gate_reason` | `gate`, `gateReason` | `gate`, `gateReason` | `gate`, `gateReason` |
| L7 verdict, mode, rule kind, policy id | `l7_verdict`, `l7_mode`, `l7_rule_kind`, `l7_policy_id` | `l7Verdict`, `l7Mode`, `l7RuleKind`, `l7PolicyId` | same as CEF | same as CEF |

State-change records carry `from_state` / `to_state` (JSON-lines), `oldState` /
`newState` (LEEF), and `fromState` / `toState` (syslog).

Not written by any of the four formats in 2.24.0, although the exporters accept
them: caller type (`human`, `agent`, `service`, `anonymous`), caller id, and the
cost-attribution fields (`cost_cents`, `cost_model`, `cost_input_tokens`,
`cost_output_tokens`).
