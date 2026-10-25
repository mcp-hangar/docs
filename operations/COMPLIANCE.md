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

The examples below are records written by core 2.34.2 for a call to `add` on a
server named `math` by the principal `user:developer` (principal type `user`,
role `developer`), and for that server's state change from `cold` to `ready`.

### CEF (Common Event Format)

```text
CEF:0|MCP Hangar|MCP Hangar|2.34.2|101|Tool Invocation Completed|1|rt=1792940002270 dvchost=mcp-hangar act=ToolInvocationCompleted cs1=math cs1Label=ProviderID suser=user:developer spriv=developer flexString1=math flexString1Label=RouteBackend suid=user:developer flexString2=user flexString2Label=CallerType cs5=add cs5Label=ToolName cn1=0.31 cn1Label=DurationMs
CEF:0|MCP Hangar|MCP Hangar|2.34.2|202|Provider State Changed|3|rt=1792940002270 dvchost=mcp-hangar act=ProviderStateChanged cs1=math cs1Label=ProviderID msg=cold -> ready
```

Signature IDs: `101` completed, `102` failed, `103` denied, `202` state change.
The device-version field is the running release. A CEF state-change record
carries the transition in `msg` (`cold -> ready`). Before 2.27.3 the device
version was a fixed `0.15.0` and a CEF state change named only the server.

Compatible with ArcSight, Splunk, QRadar, and any CEF-aware SIEM.

### LEEF 2.0 (IBM QRadar)

```text
LEEF:2.0|MCP Hangar|MCP Hangar|2.34.2|101|\tdevTime=Oct 25 2026 14:53:22\tproto=tool\tusrName=user:developer\trole=developer\taction=add\tduration=0.31\tcallerType=user\tcallerId=user:developer\tsrc=math\trouteBackend=math
LEEF:2.0|MCP Hangar|MCP Hangar|2.34.2|202|\tdevTime=Oct 25 2026 14:53:22\tproto=provider\toldState=cold\tnewState=ready\tsrc=math
```

Tab-delimited extensions following the LEEF 2.0 specification (`\t` above
stands for a tab). Event IDs match the CEF signature IDs.

### JSON-lines

```json
{"timestamp": "2026-10-25T14:53:22.271027+00:00", "event_type": "ToolInvocationCompleted", "provider_id": "math", "route_backend": "math", "tool_name": "add", "status": "success", "duration_ms": 0.31, "user_id": "user:developer", "caller_roles": "developer", "caller_type": "user", "caller_id": "user:developer"}
{"timestamp": "2026-10-25T14:53:22.271050+00:00", "event_type": "ProviderStateChanged", "provider_id": "math", "from_state": "cold", "to_state": "ready"}
```

One JSON object per line; a field with no value is left out. Fields are listed
under [Exported fields](#exported-fields).

### RFC 5424 syslog

```text
<134>1 2026-10-25T14:53:22.271068Z gateway-host mcp-hangar 21649 101 [mcp@49152 provider="math" routeBackend="math" tool="add" status="success" duration="0.31" user="user:developer" roles="developer" callerType="user" callerId="user:developer"] Tool add on provider math success
<132>1 2026-10-25T14:53:22.271090Z gateway-host mcp-hangar 21649 202 [mcp@49152 provider="math" fromState="cold" toState="ready"] Provider math state changed from cold to ready
```

Facility `local0`; severity informational for a completed call, error for a
failed one, warning for a refusal or a state change. HOSTNAME is the gateway's
host name, PROCID its process id, and MSGID the CEF signature ID. Suitable for
rsyslog, syslog-ng, and Fluentd syslog inputs.

## Examples

`serve --http` binds `127.0.0.1` by default (since 2.29.0); the examples name
it for a local run with auth off. A non-loopback host refuses to start without
authentication.
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
| Caller type: `user`, `service` or `anonymous` | `caller_type` | `flexString2` (label `CallerType`) | `callerType` | `callerType` |
| Caller id: the user id, else the agent id | `caller_id` | `suid` | `callerId` | `callerId` |
| Cost, in hundredths of a cent | `cost_cents` | `cn2` (label `CostCents`) | `costCents` | `costCents` |
| Pricing model | `cost_model` | (none) | `costModel` | `costModel` |
| Input tokens | `cost_input_tokens` | `cn3` (label `CostInputTokens`) | `costInputTokens` | `costInputTokens` |
| Output tokens | `cost_output_tokens` | `flexNumber1` (label `CostOutputTokens`) | `costOutputTokens` | `costOutputTokens` |
| Session | `session_id` | `cs3` | `sessID` | `session` |
| Tenant | `tenant_id` | `cs6` | `tenantID` | `tenant` |
| Upstream error (the upstream JSON-RPC error code, e.g. `-1`) | `error_type` | `reason` | `reason` | `error` |
| Refusing gate and its reason code | `gate`, `gate_reason` | `gate`, `gateReason` | `gate`, `gateReason` | `gate`, `gateReason` |
| L7 verdict, mode, rule kind, policy id | `l7_verdict`, `l7_mode`, `l7_rule_kind`, `l7_policy_id` | `l7Verdict`, `l7Mode`, `l7RuleKind`, `l7PolicyId` | same as CEF | same as CEF |

State-change records carry `from_state` / `to_state` (JSON-lines), `msg`
(`<from> -> <to>`, CEF), `oldState` / `newState` (LEEF), and `fromState` /
`toState` (syslog).

The caller and cost fields are written by all four formats since 2.28.0; before
it the exporters accepted them and wrote none. A call with no identity (auth
off) carries no caller fields, and the cost fields appear only when a cost was
attributed to the call. Every labelled CEF string slot is taken, so CEF has no
field for the pricing model; the other three formats carry it.
