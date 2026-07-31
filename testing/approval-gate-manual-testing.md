# Manual Testing Guide: Approval Gate

## Prerequisites

- Python 3.11+ with `uv` installed
- Node.js 18+ (for dashboard)
- mcp-hangar checked out on `main`
- Optional: Slack workspace with webhook configured

---

## 1. Configuration

### 1.1 Dashboard Channel (default)

Add to your `config.yaml`:

```yaml
enterprise:
  approvals:
    channel: dashboard
```

### 1.2 Slack Channel

```yaml
enterprise:
  approvals:
    channel: slack
    slack:
      webhook_url: "https://hooks.slack.com/services/T.../B.../xxx"
      signing_secret: "your-slack-signing-secret"
```

### 1.3 NoOp Channel (for testing without notifications)

```yaml
enterprise:
  approvals:
    channel: noop
```

---

## 2. Policy Configuration

Add `approval_list` to a MCP server's tool access policy:

```yaml
mcp_servers:
  grafana:
    tool_access_policy:
      deny_list:
        - "admin_*"
      approval_list:
        - "delete_*"
        - "create_alert_rule"
      approval_timeout_seconds: 300
      approval_channel: dashboard
```

### Policy Precedence

| List           | Effect          |
|----------------|-----------------|
| `deny_list`    | Blocked (highest) |
| `approval_list`| Held for approval |
| `allow_list`   | Immediate execution |
| (none)         | Unrestricted    |

A tool on `deny_list` is always blocked -- even if also on `approval_list`.

---

## 3. Test Scenarios

### 3.1 Approve Flow (Dashboard)

**Steps:**

1. Start mcp-hangar:

   ```bash
   cd mcp-hangar && uv run mcp-hangar
   ```

2. Start the dashboard:

   ```bash
   cd hangar-app && npm run dev
   ```

3. Open the dashboard at `http://localhost:5173`

4. Navigate to **Approvals** in the sidebar (under Governance)

5. From an MCP client (e.g., Claude Code), invoke a tool matching the `approval_list` pattern:

   ```
   delete_dashboard(id="dash-123")
   ```

6. Observe in the dashboard:
   - The "Approvals" page shows a new pending request
   - Card shows: MCP server ID, tool name, countdown timer, arguments
   - Badge shows pending count

7. Click **Approve**

8. Observe:
   - The tool execution completes in the MCP client
   - The card moves to "Approved" tab
   - The card shows `decided_by` info

**Expected Result:** Tool executes successfully after approval.

### 3.2 Deny Flow (Dashboard)

1. Invoke a tool matching `approval_list`
2. In the dashboard, expand the card and optionally enter a deny reason
3. Click **Deny**

**Expected Result:** MCP client receives an error response with `error_code: "approval_denied"` and the deny reason.

### 3.3 Timeout Flow

1. Set `approval_timeout_seconds: 10` in policy (short timeout for testing)
2. Invoke a tool matching `approval_list`
3. Do NOT approve or deny -- wait for timeout

**Expected Result:** After 10 seconds, MCP client receives error with `error_code: "approval_timeout"`, message "No response within timeout".

### 3.4 Deny-List Override

1. Configure a tool that matches BOTH `deny_list` and `approval_list`:

   ```yaml
   deny_list:
     - "admin_*"
   approval_list:
     - "admin_*"
   ```

2. Invoke `admin_reset()`

**Expected Result:** Tool is blocked immediately (deny_list wins). No approval request is created.

### 3.5 Sensitive Argument Redaction

1. Invoke a tool with sensitive arguments:

   ```
   connect_database(host="localhost", password="secret123", api_token="tok_abc")
   ```

2. Check the approval card in the dashboard

**Expected Result:** Arguments show `password: "[REDACTED]"` and `api_token: "[REDACTED]"`, while `host` shows the actual value.

---

## 4. REST API Testing (curl)

### 4.1 List Pending Approvals

```bash
curl -s http://localhost:8080/api/approvals?state=pending | jq
```

### 4.2 Get Single Approval

```bash
curl -s http://localhost:8080/api/approvals/{approval_id} | jq
```

### 4.3 Approve via API

> From 2.0.0 resolution is authorized: the caller must present a token whose
> principal holds `approval:resolve`. The `x-principal-id` header these steps
> used to send no longer sets identity — it was never authentication, and a
> client-supplied value landing in the provenance chain is what 2.0.0 removed.
> Export `TOKEN` before running the calls below. On a gateway started with
> `--unsafe-no-auth` the header is unnecessary and the decision is attributed
> to the system principal.


```bash
curl -X POST http://localhost:8080/api/approvals/{approval_id}/resolve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"decision": "approve"}'
```

### 4.4 Deny via API

```bash
curl -X POST http://localhost:8080/api/approvals/{approval_id}/resolve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"decision": "deny", "reason": "Not authorized for production"}'
```

### 4.5 Double Resolve (idempotency check)

After resolving once, send the same request again:

```bash
# Should return 409 Conflict
curl -s -o /dev/null -w "%{http_code}" -X POST \
  http://localhost:8080/api/approvals/{approval_id}/resolve \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve"}'
```

**Expected:** HTTP 409

---

## 5. Slack Integration Testing

> **This section changed in 2.0.0.** Core no longer terminates a Slack webhook.
> Pointing Slack's Request URL at the resolve endpoint, as earlier revisions of
> this page instructed, sends an unverified request to an endpoint that no
> longer checks Slack signatures. Delivery now runs as an adapter you deploy;
> see [Approval delivery adapters](../guides/APPROVAL_ADAPTERS.md).

### 5.1 Prerequisite Setup

1. Install a delivery adapter that registers under the
   `mcp_hangar.approvals.delivery` entry-point group, and configure
   `approvals.channel` to the name it registers.
2. Create a Slack App with Interactivity enabled.
3. Set the Request URL to **the adapter's** callback endpoint, not Hangar's.
4. Give the adapter the Signing Secret and a Hangar token whose principal holds
   `approval:resolve`.

With no adapter installed, an unknown channel degrades to `noop` and logs a
warning: approvals queue undelivered but stay resolvable over REST. That is the
intended behaviour, not a failure to debug.

### 5.2 Notification Test

1. Configure the adapter's channel in config.
2. Invoke a tool matching `approval_list`.

**Expected:** Slack message appears with:

- Header: "Approval Required"
- MCP Server and tool name
- Sanitized arguments in a code block
- Expiry countdown
- "Approve" (green) and "Deny" (red) buttons

### 5.3 Slack Approve/Deny

1. Click **Approve** or **Deny** in Slack.
2. Verify the adapter verified the Slack signature and called
   `POST /api/approvals/{approval_id}/resolve` with its token.
3. Verify the tool execution completes (or fails with denied).
4. Verify `decided_by` names the **Hangar principal** the adapter mapped the
   Slack user onto. The old `slack:{user_id}` form is retired: provenance names
   a principal Hangar authenticated, not a vendor handle.

---

## 6. Permission Verification

### 6.1 Roles

| Role            | Can view approvals | Can resolve |
|-----------------|-------------------|-------------|
| mcp_server_admin  | Yes               | Yes         |
| auditor         | Yes               | No          |
| viewer          | No                | No          |

### 6.2 Test Steps

1. Log in as `auditor` role
2. Navigate to Approvals page -- should see pending requests
3. Try to approve -- should be blocked (no `approval:resolve` permission)

4. Log in as `mcp_server_admin`
5. Navigate to Approvals page
6. Approve/Deny -- should succeed

---

## 7. Domain Event Verification

After each approval action, verify events in the event store/log:

| Action   | Expected Event            |
|----------|--------------------------|
| Request  | `ToolApprovalRequested`  |
| Approve  | `ToolApprovalGranted`    |
| Deny     | `ToolApprovalDenied`     |
| Timeout  | `ToolApprovalExpired`    |

Check via:

```bash
# If event store exposed via API:
curl -s http://localhost:8080/api/events?type=ToolApprovalRequested | jq
```

Or check server logs for `approval_id` entries.

---

## 8. Automated Test Suite

Run all approval-related tests:

```bash
cd mcp-hangar

# Unit tests (106 tests)
uv run pytest tests/unit/domain/value_objects/test_tool_access_policy_approval.py \
  tests/unit/enterprise/approvals/ -v

# Integration tests (14 tests)
uv run pytest tests/integration/test_approval_flow.py \
  tests/integration/test_approval_api_e2e.py -v

# Fuzz tests (serialization round-trip)
uv run pytest tests/unit/test_event_serialization_fuzz.py -v

# Enterprise boundary check
bash scripts/check_enterprise_boundary.sh
```

---

## 9. Checklist

- [ ] Approve flow works via dashboard
- [ ] Deny flow works with reason
- [ ] Timeout expires correctly
- [ ] deny_list overrides approval_list
- [ ] Sensitive args are redacted
- [ ] REST API returns correct status codes (200, 400, 404, 409)
- [ ] Double resolve returns 409
- [ ] Slack notifications arrive (if configured)
- [ ] Slack buttons resolve correctly
- [ ] mcp_server_admin can resolve, auditor can only view
- [ ] Domain events published for all transitions
- [ ] Concurrent approvals do not interfere
- [ ] All automated tests pass (unit + 14 integration)
