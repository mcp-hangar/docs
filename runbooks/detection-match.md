# Runbook: critical detection rule match

**Alert:** `MCPHangarCriticalDetectionMatch` (critical) — `mcp_hangar_detection_rule_matches_total{severity="critical"} > 0`.

## What it means

A security detection rule matched at **critical** severity — a governance/security
signal, not a reliability one. Something a policy considers dangerous happened.

## Impact

Potential security event. Depending on `enforcement mode`, an enforcement action
(alert / block / quarantine) may already have been taken.

## Diagnose

```promql
sum by (rule_id, severity) (rate(mcp_hangar_detection_rule_matches_total[15m]))
sum by (action, rule_id) (rate(mcp_hangar_enforcement_actions_total[15m]))
sum by (mcp_server, violation_type) (rate(mcp_hangar_capability_violations_total[15m]))
```

Correlate with the audit trail: the same events are exported to SIEM (LEEF 2.0 /
RFC 5424 / CEF) and as OTLP audit logs — pull the matching records by `rule_id`.

## Remediate

1. Identify the `mcp_server` and `rule_id`; determine if it's a true positive.
2. True positive → contain (block/quarantine the server), preserve the audit records, follow the security incident process.
3. False positive → tune the detection rule; do not silence the alert blindly.

## Escalate

Page the security on-call for any confirmed critical match.
