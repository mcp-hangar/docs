<!-- verified-against: 2.31.0 -->

# What a Verdict Establishes

Hangar's thesis is that every tool call ends in a verdict. This page is the other
half of that: what a given verdict **proves** to someone reading it later — an
auditor with a SIEM export, a second team holding a drift event, a reviewer of an
approval record.

A verdict is three things: an **outcome**, a **reason**, and the **rule that
produced it**. Read a record with all three, and note what is *not* in it. The
columns below are the shape
[`COMPLIANCE_POSTURE.md` §5](../operations/COMPLIANCE_POSTURE.md) already uses
for the legal layer, applied to the enforcement layer: **establishes / does not
establish / left to the operator**.

Nothing here is forward-looking. Every "establishes" claim is backed by code or
an ADR, and anything not shipped appears only in the middle column.

**Reviewed against 2.31.0.** Every row below was re-checked against the
release notes and the code of 2.30.0 and 2.31.0. What moved since the 2.29.1
review: a tool that drifted from a `block` pin is withheld from every listing a
model reads, and its front-door call is answered like a call of a tool that
does not exist (2.30.0); a drift is published once when a catalogue first shows
it, with the periodic re-check off too (2.30.0); a tool under a `block` pin is
served with only the four fields its digest covers (2.30.0); and a held call
can be approved or denied with `mcp-hangar approvals`, as the declared stdio
principal (2.31.0); and an authenticated front-door caller is listed
`hangar_whoami` whatever its grants (2.31.0). Rows corrected for it: digest pin
passed, digest mismatch, the listed digest, approval `approved`, tool access,
the empty projection and projection withdrawal --
see
[what a record from before 2.30.0 lacks](#what-a-record-from-before-2300-lacks).
The digest pin row also left `title` out of the fields the digest does not
cover, a slip in the earlier reviews. Hot-load trust (2.30.0:
`hot_loading.trusted_namespaces`, the secrets allowlist,
`allow_force_unverified`, `is_official` renamed `is_published`), the
removal of `PolicyPushRejected` and the narrower
`hangar.shaping.mutation` events (2.31.0) change no verdict on this page. No
verdict was removed.

**Added for 2.32.** The key-pinned upstream row (ADR-030, core 2.32.0, with the
2.32.1 corrections it names). The other rows have not been re-reviewed against
2.32.x yet; that review is still against 2.31.0.

**The 2.29.1 review.** Every row was re-checked against the
release notes of 2.27.1 through 2.29.1. What moved since the 2.27.0 review:
a pin can be bound to the upstream it was taken from (2.28.0), a tool that
appears after the pins were taken can be withheld until it is pinned (2.28.0,
a new row), a pin check and the periodic re-check now read every page of a
paginated `tools/list` (2.28.0), an approval granted and then cancelled before
the call ran is recorded `cancelled` (2.28.0), and an enforced L7 refusal no
longer starts a cold server first (2.29.0). A misspelled `digest_enforcement`
or a malformed `tool_projection` block now refuses the configuration (2.29.1)
instead of running on the default mode. Rows corrected for it: digest pin
passed, digest mismatch, approval `approved` and `cancelled`, L7 Enforce, and
projection withdrawal. No verdict was removed.

**The 2.27.0 review.** Every row was re-checked against the code that release
ships. What moved since the 2.25.0 review is one row: a passed
SSRF check on an API-registered endpoint can now mean a private address inside
a network the deployment trusts (`ssrf.trusted_networks`), not only a public
one. 2.26.0 changed no verdict: refusing an API delete of a server the
configuration declares (`409 declared_in_config`) moves no record.

**The 2.25.0 review.** What moved since the 2.24.0 review: a pinned server's
catalogue is re-listed on an interval, so the digest rows no longer depend on a
restart to see unannounced drift; an approval that arrives after its call was
cancelled is recorded `cancelled`, not `approved`; an invalid tool access
policy refuses the configuration instead of being dropped; the actor of an auth
change is the authenticated caller, not the request body; and a SIEM export the
gateway cannot perform refuses startup instead of dropping records. Rows
corrected for it: digest mismatch, approval `approved` (and a new `cancelled`
row), tool access and auth -- see
[what a record from before 2.25.0 lacks](#what-a-record-from-before-2250-lacks).

**The 2.24.0 review.** What moved since the 2.22.0 review is the **audit** side: a
refused call now leaves an audit record of its own (`ToolCallRefused`, exported
as a `denied` tool invocation), a group call's record names the group, an
allowed call's record names the role that admitted it, and the front door's
flat `tools/call` now checks `tool:invoke`. Spans gained the L7 verdict and lost
the caller's own ids by default. Rows corrected for it: the listed digest (new),
approval `approved`, L7 Enforce, L7 Audit, any L7 verdict, the `Mcp-Param-*` selector, tool
access and auth -- see
[what a refusal leaves since 2.24.0](#what-a-refusal-leaves-since-2240). The
tool access row also named the wrong log line for a front-door denial, a slip
present since 2.22.0.
A record is only as good as the gateway that wrote it: read
[what a record from before 2.30.0 lacks](#what-a-record-from-before-2300-lacks)
before trusting a listing or a drift record a 2.29.x or earlier gateway
produced,
[what a record from before 2.25.0 lacks](#what-a-record-from-before-2250-lacks)
before trusting anything a 2.24.x or earlier gateway produced,
[what a record from before 2.24.0 lacks](#what-a-record-from-before-2240-lacks)
before trusting an export a 2.23.x or earlier gateway produced, and
[the three rows that were weaker before 2.16.0](#three-rows-that-were-weaker-before-2160)
before reading anything a 2.15.0 or earlier gateway produced.

## The table

| Verdict | Establishes | Does not establish | Operator's side |
| --- | --- | --- | --- |
| **Digest pin passed** | the tool's `{name, description, inputSchema, outputSchema}` is byte-identical (RFC 8785 JCS) to the pinned one. Since 2.28.0, when the pins carry `tool_projection.upstream` (written by `mcp-hangar pin --write`), also that the server's upstream is the one they were taken from: the origin of a remote endpoint, the image of a container, or the executable and a hash of the command line of a subprocess. Since 2.30.0, under `block`, also that no listing served the tool more than those four fields and Hangar's own (`digest`, `pinned_digest`): the front door's `tools/list` on stdio and streamable HTTP, `server/discover`, `hangar_tools`, `hangar_details` and the REST server and tool routes all cut it through one allow-list (`tool_projection.PINNED_TOOL_FIELDS`, `ToolProjectionRegistry.served_definition`), for a pin on the server, on a group that owns it or for the caller's tenant | the tool is safe; that `title`, `annotations`, `execution`, `icons` or `_meta` are unchanged -- the digest does not cover them. Since 2.30.0 a tool under a `block` pin is served without them, so a client reads the spec's defaults for the hints (`readOnlyHint: false`, `destructiveHint: true`) and `name` for the display name; under `warn` or `audit`, and for an unpinned tool, they are served as the upstream sent them; that the upstream *implements* the schema it declares; **that an empty-valued field is unchanged** — `None` / `""` / `{}` / `[]` are dropped before canonicalization (`digest_computation._is_meaningful`), so gaining `description: ""` or losing `outputSchema` to `{}` moves nothing; **that pins written without `upstream` say anything about which upstream served the tool** -- they check the definition only, so a pin block copied to another server passes there | pin provenance: since 2.18.0 `mcp-hangar pin --write` records what a server served at a moment nobody else witnessed, so *who ran it, and against which upstream* is the operator's to keep; who approved the digest -- since 2.28.0 the event log keeps a pin history (`ToolPinRecorded`, `ToolPinRevoked`, read with `mcp-hangar why --tool NAME`), and it records the approver of a pin written in the configuration as `config`, because the file carries no author |
| **`pin --check` clean** *(2.18.0)* | at the moment the command ran, every tool named in `tool_projection.pins` was served with the digest the file records — computed by `compute_tool_digest`, the same function the gate compares against, so a clean check and a passing call agree by construction rather than by two implementations | that it still holds: an upstream can change between the check and the call, which is what the gate is for; anything about a tool that is served and **not** pinned — `pins` is a subset by design and an unpinned tool is not drift; that the servers behave as their schemas say | which tools are pinned at all; running the check where it can fail loudly (exit 1) rather than only before a release |
| **Digest mismatch / unknown** | the contract moved, or was never pinned; the record carries expected, observed, `enforcement`, `correlation_id`, `tenant_id`; since 2.28.0 the `domain_event` log line also carries `expected_digest` and `observed_digest` (a tool with no pin has no `expected_digest`), and an upstream that differs from the one the pins were bound to is a mismatch whatever its tools say, with `expected_upstream` and `observed_upstream` on the event. Since 2.25.0 a pinned READY server is re-listed every `tool_projection.pin_recheck_interval_s` (60 s by default), and the pass that first sees a drifted pin publishes one `DigestMismatchEvent` with `correlation_id` `pin_recheck` and logs `tool_digest_pin_drift_detected`, before anyone calls the tool. Since 2.30.0 the same one event and line follow any catalogue build that shows the drift -- at start, on `tools/list_changed`, after a reload -- with the re-check off too (`PinRecheckWorker.report_drift`, a projection change listener). Since 2.30.0, under `block`, a drifted tool is also withheld from every listing a model reads -- the front door's `tools/list` on stdio and streamable HTTP, `server/discover` and `hangar_tools` -- with `notifications/tools/list_changed` sent when it goes and when it returns; `hangar_details` names it under `withheld_tools` with `reason: digest_drift`, `digest` and `pinned_digest` and without its description, and the REST tool routes show it as its name, digests and `withheld: "digest_drift"`. A front-door call of it is answered `-32601`, like a tool that does not exist; `hangar_call` still refuses it with `ToolDigestMismatchError` | that the change is hostile; whether the caller was served or refused — read `enforcement`, where `DigestEnforcement.BLOCK` is the only blocking value, and the only one that withholds: under `warn` and `audit` the drifted tool stays listed, description and all; **that a front-door call of a withheld tool left a record** -- since 2.30.0 it is answered before the digest gate, so it publishes no `DigestMismatchEvent` and no `ToolCallRefused` -- its record is a `front_door_tool_call` line with `outcome=not_found` -- and the drift's record is the one event its catalogue build published; that a tool served by another upstream than its pins were bound to is withheld -- a listing compares the SHA-256 only (`drifted_pin`), so such a tool stays listed and is refused at the call; **that a missing event means no drift** -- unannounced drift is seen at most one interval plus the listing time after it happened, never with the interval at `0`, not while the server is `cold`, degraded or DEAD, and not while its listing fails (`pin_recheck_failed`); since 2.28.0 a paginated listing is read to its last page, at most 50 pages, and a walk cut short logs `tools_list_pagination_stopped`, so a tool beyond the cut is still unchecked | `block` vs `warn` -- since 2.30.0 also whether a drifted tool is listed at all; re-pinning (`mcp-hangar pin --write`) after reviewing the new definition at the upstream, which returns the tool; the `unknown` policy (`ALLOW_UNVERIFIED` returns valid and emits no event at all) |
| **Listed `digest` / `pinned_digest`** *(2.24.0)* | the tool as this listing returned it hashes to `digest` under `compute_tool_digest`, the function `pin` and the gate use; `pinned_digest`, when present, is the pin found for the id the caller named, then for the group member that served the listing -- on `hangar_tools` for the caller's tenant or all tenants, on `GET /api/tools` and `GET /api/mcp_servers/{id}/tools` the all-tenants pin only. A pair that differs is drift, read without the CLI -- since 2.30.0 on `hangar_tools` only under `warn` or `audit`, because a tool that drifted from a `block` pin is not listed there; it is in `hangar_details` `withheld_tools`, and on the REST routes as its name, `digest`, `pinned_digest` (when an all-tenants pin is on the server) and `withheld: "digest_drift"`, with no description or input schema. REST marks it `withheld` when it drifted from a `block` pin for any tenant, on the server or on a group that owns it (`drifted_for_any_tenant`) | that a call will be refused or served -- the gate decides at call time, and the upstream can change between the listing and the call; that the upstream serves this schema when the server has predefined tools -- the listing, and so the digest, is the schema the configuration declares; **that a missing `pinned_digest` means no pin** -- a pin a member inherits from a group that owns it is not shown, and a per-tenant pin is not shown on the REST routes, so a `withheld` entry there with no `pinned_digest` drifted from a group's or a tenant's pin; that a tool missing from `hangar_tools` is not served by the upstream -- since 2.30.0 it may be withheld for drift; that the listed definition is the upstream's whole definition -- since 2.30.0, under a `block` pin, it is the four digested fields; anything about a tool the caller cannot list, which carries neither field and is not named in `withheld_tools` | reading `pinned_digest` against `tool_projection.pins`, the file that is the pin's source |
| **Approval `approved`** | one principal (`decided_by`) resolved this `approval_id` before `expires_at`; at dispatch the state, the expiry and a hash of the **raw** arguments were re-checked (`ApprovalGateService.revalidate`). Since 2.31.0 the decision may have been made with `mcp-hangar approvals approve` against the approval store the gateway shares: `decided_by` is then the `auth.stdio.principal` declared in the configuration the command read, and the decision went through the same `ResolveApprovalHandler` as `POST /api/approvals/{id}/resolve`, with the same expiry, compare-and-swap and tenant scoping; the gateway holding the call publishes `ToolApprovalGranted` when its poll reads the record | that the approver saw the raw arguments — they saw a redacted copy, on the CLI too; **over the CLI, who decided, or that the gateway's own configuration declared them** -- the command presents no credential, and `--config` and `--db` are independent, so `decided_by` names the principal declared in whatever configuration it was given, and its `approval:resolve` check runs in the invoking process, never again in the gateway that reads the record; a CLI decision establishes write access to the approval store, which is also all a direct write to that file needs; that the approver was competent or authorized in any legal sense; that the call was dispatched — an approval granted and then overtaken by a cancel during the re-checks after the hold, or during the cold start, publishes `ToolApprovalGranted` (the human did approve) and is then moved to `cancelled` (since 2.28.0, next row); an approval that arrives after the batch's deadline has passed reads `CancellationError` and is not dispatched, and since 2.25.0 is recorded `cancelled` instead (next row), but an approval resolved on a different instance from the one holding the call -- or with the CLI -- answers `200` with `approved` there (the CLI prints it approved) before the holder records it `cancelled`; that the call then succeeded | who may resolve -- for the CLI, who can write the approval store, which the file's permissions decide; the roles under `auth.stdio.principal.roles` must hold `approval:resolve` (`provider-admin` or `admin`; `viewer`, the role `init` declares, is refused), even with auth off; channel delivery; hold timeout |
| **Approval `cancelled`** *(2.25.0)* | the held call's `hangar_call` batch was cancelled before an approval arrived, and the call did not run: the resolve answered `409` with `state: "cancelled"` (or, resolved on another instance, the holder recorded it), and the gate published `ToolApprovalCancelled` instead of `ToolApprovalGranted`. Since 2.28.0 a cancel that comes **after** the approval -- during the re-checks that follow the hold, or the cold start -- publishes `ToolApprovalGranted` first, then moves the record from approved to cancelled and publishes `ToolApprovalCancelled` with the reason "approved, then the call was cancelled before it ran", so the stream holds both events for one `approval_id` and the later one decides. `decided_by` and the event's `attempted_by` name who tried to approve it | that anyone let the call through -- nothing did; anything about a call whose hold ended in a denial or an expiry after the deadline, which is still recorded as that | a client or dashboard that reads every `409` as "already resolved" reading `state` instead |
| **Approval `expired` / `denied`** | the call was not dispatched through this gate | anything about whether it was attempted elsewhere | — |
| **L7 egress `deny` (Enforce)** | the call was refused before reaching the upstream -- since 2.29.0 without starting a cold server first; before, a denied call spawned the server and left it READY -- and the refusal is recorded: `EgressPolicyEnforced` carries tool, server, `action`, reasons, `rule_kind`, `policy_id`, `correlation_id`, `identity_context`; `mcp_hangar_egress_policy_enforced_total{action,rule_kind}` counts it; a `batch_call_refused` warning carries the verdict as bounded fields (`l7_verdict`, `l7_mode`, `l7_rule_kind`, `l7_inspection_failed`, `policy_id`) rather than the reasons, since 2.24.0; and since 2.24.0 the call has an audit record, `ToolCallRefused`, with `hangar.l7.verdict`, `hangar.l7.mode`, `hangar.l7.rule_kind` and `hangar.l7.policy_id` | that traffic did not reach the destination by another path; that established connections were cut — they are not (conntrack, see [EGRESS_POLICY](../guides/EGRESS_POLICY.md)); the reasons — they are on the event and the aggregate's `egress_policy_enforced` warning only, never on a span, the `batch_call_refused` line or the audit record. A deny because the arguments **could not be inspected** (`rule_kind` `arguments`) is still refused and still in `EgressPolicyEnforced`, but reads as a failure everywhere else: `batch_call_failed` at warning, a span that ends ERROR with `hangar.call.outcome=error`, and no `ToolCallRefused` | backstop flavour; pod restart after switching to `Enforce` |
| **L7 `deny` observed (Audit)** | the policy *would* have refused: `EgressPolicyViolationObserved` carries the same fields, with `would_be_action` in place of `action` and no `rule_kind`, and `mcp_hangar_egress_policy_violations_observed_total` counts it; since 2.24.0 the call's span reads `hangar.l7.verdict=audit_observed` | that anything was blocked — Audit falls through and the call proceeds | the decision to switch to `Enforce` |
| **Any L7 verdict** | which policy produced it: `policy_id` is a content hash of the compiled rules, carried by the verdict, by the refusals and by `EgressPolicySet` -- and since 2.24.0 by the call's span (`hangar.l7.policy_id`) and a refusal's audit record -- so a record and a policy change join on a value rather than on adjacent timestamps | that the *rules* are visible in the record — the id resolves to them only against a gateway still holding that policy (`GET /api/mcp_servers/{id}/l7_policy` returns `policyId`) | keeping the policy documents that ids were computed from |
| **L7 verdict by `Mcp-Param-*` selector** | the header matched a rule **and** the header was validated against the request body: only the front door binds a header for the policy, only one the called tool declares with `x-mcp-header`, only after re-running the SDK's check, and as the SDK decoded it (a `=?base64?...?=` sentinel included) | anything on a request where a header was not checked — `hangar_call` (it declares no header), a handshake-era request, a skipped or failed validation, a state that does not say validation ran: none of these headers reaches a selector, and the call falls through to the tool rules and the policy default ([ADR-025](../adr/ADR-025-header-selectors-must-not-match-unvalidated-headers.md)); the fall-through is visible as `rule_kind` `tool` and in the verdict reasons ("header rules not consulted", on the event), not in the absence of one. A checked header beside an unchecked one still decides, with that reason added | `headers.param_validation.required`, which refuses a modern-revision call carrying an `Mcp-Param-*` header that did not reach the selector rather than serving it; a handshake-era call is served with its headers ignored |
| **Tool access `denied`** | this caller cannot call this tool. Since 2.25.0 the policy behind it is the one written: a policy with an invalid field, or a list that is not a list, refuses the boot and the reload instead of being dropped or misread | that the tool does not exist — **at the front door**, withdrawn, denied, unknown and -- since 2.30.0 -- drifted from a `block` pin are all `-32601`, deliberately (shown equals callable, [ADR-022](../adr/ADR-022-the-management-surface-is-what-the-caller-may-call.md)). On the batch surface the answer differs: `ToolAccessDeniedError`, "Tool not available for this mcp_server". **A front-door denial leaves no audit record**: it is answered before the executor runs, so there is no `ToolCallRefused` and no `batch_call_refused` for it | reading the operator-side log, which carries the reason the client is not given. At the front door that is `front_door_tool_call` at info with `outcome=not_found` and `reason=not_projected` (`unknown` when no upstream holds the name); since 2.30.0 `not_projected` also covers a tool withheld for drift, which `hangar_details` `withheld_tools` names. On the batch surface — and at the front door for a tool denied between the listing and the call — it is `batch_call_refused` at warning, carrying `gate=tool_access` and `reason=tool_not_in_access_policy` (the per-gate `tool_access_denied` line is still written, at debug), and since 2.24.0 a `ToolCallRefused` audit record with the same gate and reason |
| **Empty projection (`{"tools": []}`)** | nothing about whether the caller is allowed anything | which of `no_identity` (a fail-closed deny), `nothing_discovered` (a replica whose warm-up has not finished or did not succeed) or `filtered` (the honest empty) produced it — indistinguishable from outside, classified only on the operator's side: in the log line and in the `reason` label of `mcp_hangar_empty_projection_total`; since 2.30.0 `filtered` does not separate a policy that allows nothing from a catalogue whose every tool the caller may call is withheld for drift from a `block` pin. Since 2.31.0, on a `front_door` gateway with auth on, an authenticated caller allowed no upstream tool is listed `hangar_whoami`, which needs no permission, so its empty projection reads as that one name rather than `[]`, and is still counted as empty -- the count is of upstream tools alone | reading that log line before treating `[]` as a policy result |
| **SSRF check passed** | the endpoint resolved to a permitted range at registration and, for an API-registered `remote` server, again at connect — `_SsrfGuardedTransport` re-resolves and pins per request. Since 2.27.0 a permitted range includes a private network listed in `ssrf.trusted_networks`, checked against the list in force at each connect, so a reload that narrows it refuses the next connection | that the endpoint is public -- with `ssrf.trusted_networks` set it may be any address in those networks, for every caller allowed to register a server; anything about `remote` endpoints declared in `config.yaml` ([ADR-021](../adr/ADR-021-config-file-endpoints-outside-the-ssrf-policy.md)) — the boot warning names each one, a hostname included (`ssrf_policy_not_applied_to_config_file_endpoint`), but it warns and does not refuse | knowing that moving an upstream into the config file drops both halves; how narrow `ssrf.trusted_networks` is -- a Kubernetes Service range holds the kube-apiserver's ClusterIP |
| **Auth `401` / `403`, `tool:invoke` denied** | the credential was not accepted, or the principal lacks the permission. A `tool:invoke` denial of a tool call is not an HTTP status: it is `Not authorized to invoke tool '<tool>': tool:invoke permission required` — a failed batch entry (`AuthorizationDenied`) on `hangar_call`, and since 2.24.0 a tool error (`isError`) on the front door's flat `tools/call` — and since 2.24.0 one `ToolCallRefused` with `gate=authorization` and reason `tool_invoke_denied` or `unauthenticated`. An allowed call's audit record carries `mcp.caller.roles` *(2.24.0)*: the role the allow decision matched, or `opa_policy` | over stdio, that anyone presented a credential — the principal is the one `auth.stdio.principal` declares, trusted because the process was spawned ([ADR-026](../adr/ADR-026-stdio-is-an-authenticated-transport.md)); what the matched role grants, or granted when the call was made; any role on a trace — `mcp.caller.roles` is on the audit record only, and absent with auth off | role mapping; the stdio declaration. Since 2.25.0 a key or role change is recorded against the principal that made it (`anonymous` with auth off); before, the request body named the actor |
| **Key-pinned upstream verified** *(2.32.0)* | the TLS connection that served the call ended at a key whose `SubjectPublicKeyInfo` hashes to a pin on the server's list (`tls.peer_identity.spki_sha256`), checked inside the handshake before the first request byte, under TLS 1.3, on every connection the transport makes: the first call, a retry, a reconnect, a pool replaced after `max_connection_age` and the GET stream. A served call's record carries `upstream_peer_spki`, the verified key; a refused one carries `observed_peer_spki`, the key the peer presented -- on a cold start a `ToolCallRefused`, exported `denied` with reason `upstream_peer_key_mismatch`; on a warm connection a `ToolInvocationFailed`, exported `error` with `failure_code: upstream_peer_key_mismatch`. `mcp_hangar_upstream_peer_key_connections_total{outcome}` counts the handshakes. Digest pins bound to `peer-key:<key_ref>` name the lineage, not the address. Since 2.32.1 the pin is taken over the key as the certificate encodes it, so the `openssl` pipeline gives the value compared | who controls the key, or how it came to be listed -- this is operator-declared trust: whoever holds `mcp_servers:peer_identity` or writes the configuration file can list a key they control, and with authentication off any API client can; anything a CA would say -- no chain and no hostname is checked; that a listed key was not stolen -- it is trusted until it leaves the list, and on each replica until that change reaches it; attestation of any kind -- `issuance: kbs-attested` is refused by core 2.32.x, and would be a declaration Hangar does not verify (ADR-030 §2); anything about a configuration-file server on a release before 2.32.0, which serves it as a plain one | the list and its rotation (add the next key, then remove the old one; a disjoint list under the same `key_ref` is refused); durable storage for lists set over the API; every replica on 2.32.0 or newer before the first declaration over the API, and one on 2.32.1 or newer for the database to refuse an older replica's plain write -- see [Key-Pinned Upstreams](../guides/KEY_PINNED_UPSTREAMS.md) |
| **Capability drift** | `CapabilityViolationDetected` with `violation_type`, `violation_detail` and the `enforcement_action` taken (`alert` / `block` / `quarantine`) | that the drift was hostile | which action the mode maps to |
| **Tool withheld pending admission** *(2.28.0)* | with `tool_projection.new_tools: withhold` on a server that has pins, a tool that appeared after the pins were taken is not listed on any surface and a call of it is refused like a withdrawn tool; one `ToolAdmissionRequested` event names the server, the tool and the digest of the definition waiting to be approved | that a server with no pins is covered -- it has no baseline and withholds nothing; that prompts and resources are covered -- they are not; that the default does anything -- `new_tools` is `allow` unless set; who approved a tool that was admitted, beyond the pin that admitted it (the pin ledger records the approver of a config pin as `config`) | pinning the tool to admit it (`mcp-hangar pin --write` or a pin in the config), for all tenants or the tenant that pinned it; reading `mcp-hangar why --tool NAME` for the history |
| **Projection withdrawal** | a tool was withheld, and why: `mcp_hangar_projection_withdrawals_total{reason}` — `invalid_x_mcp_header` or `header_exposure_withdraw` | that the upstream stopped offering it — the definition is still served byte-identical upstream, only the projection dropped it; that a `header_exposure_warn` sample was withheld — `warn` counts the tool and still serves it; anything about a tool withheld for drift from a `block` pin (2.30.0), which this counter does not count -- read `withheld_tools` and the digest mismatch row | `on_violation`, whose default `warn` serves the tool |

## What a refusal looks like since 2.22.0

Nothing a verdict *establishes* changed here. What changed is where the record
is, which matters to anyone holding an export or a saved query.

**One line per refusal.** Every gate that refuses a call now logs
`batch_call_refused` at warning, carrying the `gate` that refused and its bounded
`reason`
([mcp-hangar#1557](https://github.com/mcp-hangar/mcp-hangar/issues/1557)). Before
2.22.0 each gate wrote its own line under its own name -- `tool_access_denied`,
`tool_withdrawn_rejected`, `tool_digest_pin_rejected`,
`tool_digest_pin_unresolvable` -- at info. Those four are still written, at
debug, so a saved query keyed on one of them **silently returns nothing against a
2.22.0 gateway**, and against an earlier one `batch_call_refused` is absent for
everything except the two L7 refusals. 2.24.0 narrowed the line again -- see
below.

**A refusal is no longer an error trace.** The span a refused call leaves ends
UNSET rather than ERROR, and carries `hangar.call.outcome=deny`,
`hangar.refusal.gate` and `hangar.refusal.reason`
([mcp-hangar#1556](https://github.com/mcp-hangar/mcp-hangar/issues/1556)). So
**counting ERROR spans no longer counts refusals**, in either direction: an
export from 2.21.x or earlier has refusals mixed into its error traces, and one
from 2.22.0 does not. The bounded `error.type` still names what refused on both.
One exception since 2.24.0: an L7 deny because the arguments could not be
inspected ends ERROR, with `hangar.call.outcome=error`, because the evaluator
broke.

## What a refusal leaves since 2.24.0

**An audit record.** A refused call now publishes one `ToolCallRefused`
([mcp-hangar#1619](https://github.com/mcp-hangar/mcp-hangar/pull/1619)): a batch
gate that says `deny` (the tenant budget included, when its slot is taken after
the gates), a `tool:invoke` denial (`gate=authorization`), and an L7 `deny` or
`require_approval` at dispatch. The OTLP audit exporter writes it as
`tool_invocation` with `mcp.tool.status=denied`, the caller and tenant fields,
and `hangar.gate.name` and `hangar.gate.reason`, or the `hangar.l7.*` fields;
CEF, LEEF, JSON lines and syslog write it as `ToolInvocationDenied` (event id
`103` in CEF, LEEF and syslog).
It carries codes only, never the refusal's text. Three things it does **not**
establish, all of the same form -- the absence of a record:

- **Not every refusal has one.** A front-door `-32601`, a suspended session and
  a refused `Mcp-Param-*` header are answered before the executor runs, a gate
  that broke rather than refused is not a refusal, and an inspection-failed L7
  deny is not either. On the front door, its `front_door_tool_call` line is the
  record of the first three.
- **The publish is best-effort.** One that fails is logged as
  `tool_call_refused_not_published` and the call is still refused.
- **Both exports are opt-in.** The OTLP audit record is written only when an
  OTLP endpoint is set explicitly (`OTEL_EXPORTER_OTLP_ENDPOINT` or
  `observability.tracing.otlp_endpoint`) and `MCP_AUDIT_EXPORT_ENABLED` has not
  turned it off; the compliance formats only when `MCP_COMPLIANCE_FORMAT` is
  set.

**A group call's record names the group.** `mcp.server.id` on a
`tool_invocation` record is the target the caller named, and the member that
served it is `hangar.route.backend`
([mcp-hangar#1620](https://github.com/mcp-hangar/mcp-hangar/pull/1620)) -- the
names spans use. A record persisted before the change replays with the member in
both.

**Roles are on the record, not the trace.** `mcp.caller.roles` is the role the
`tool:invoke` decision matched
([mcp-hangar#1621](https://github.com/mcp-hangar/mcp-hangar/pull/1621)), and no
code path can put it on a span
([mcp-hangar#1630](https://github.com/mcp-hangar/mcp-hangar/pull/1630)). Spans
also stopped carrying the caller's user, agent and session ids by default
([mcp-hangar#1584](https://github.com/mcp-hangar/mcp-hangar/pull/1584)): they
are set only with `observability.tracing.caller_ids: true` or
`MCP_TRACING_CALLER_IDS=true`. So **a 2.24.0 trace does not say who called**
unless the operator opted in; the audit record does.

**The log line carries no gate's text.** A gate refusal's `batch_call_refused`
lost its `error` field, the message the caller is told, which some gates fill
with text they do not bound
([mcp-hangar#1589](https://github.com/mcp-hangar/mcp-hangar/pull/1589)); an L7
refusal's line keeps `error`, the fixed caller-facing message, and carries the
verdict's bounded fields in place of the policy's reasons ([mcp-hangar#1596](https://github.com/mcp-hangar/mcp-hangar/pull/1596));
and a tenant-budget refusal after the gates is now logged at all, as
`gate=tenant_budget`
([mcp-hangar#1632](https://github.com/mcp-hangar/mcp-hangar/pull/1632)). A call
that reaches its gates after the batch's budget ran out reads `batch_timeout`
from the `global_timeout` gate every time; before, it could read `cancelled`
depending on thread timing
([mcp-hangar#1591](https://github.com/mcp-hangar/mcp-hangar/pull/1591)).

**The trace shows the L7 verdict and the route.** `batch.call.<tool>` carries
`hangar.l7.verdict` (`allow`, `audit_observed`, `deny`, `require_approval`,
`approval_honored`) with the mode, rule kind and policy id, and the route:
`hangar.route.backend`, the member a group call went to, and
`hangar.route.reason`
([mcp-hangar#1595](https://github.com/mcp-hangar/mcp-hangar/pull/1595)). An L7
refusal is marked `hangar.call.outcome=deny` with those fields, not with
`hangar.refusal.gate`, which names a batch gate.

## What a record from before 2.30.0 lacks

The same rule again: a listing, a transcript or an export from a 2.29.x or
earlier gateway has the older behaviour, whatever the rows above now say.

**A refused call does not establish that the model never read the drifted
tool.** A tool that drifted from a `block` pin was refused when called, but
the front door's `tools/list` and `hangar_tools` still listed it with the
upstream's new description, on every listing
([mcp-hangar#1920](https://github.com/mcp-hangar/mcp-hangar/pull/1920)). A model
behind such a gateway may have read text the pin was there to keep out.

**A pinned tool's metadata was the upstream's.** Its `title`, `annotations`,
`execution`, `icons` and `_meta` were served as the upstream sent them under a
matching digest, so a hint a client acted on -- `readOnlyHint: true` skipping a
confirmation, say -- may have been added after the pin was taken.

**Drift records are counted differently.** A front-door call of a drifted tool
reached the digest gate, so each call left a `DigestMismatchEvent`, a
`ToolCallRefused` and a `batch_call_refused` line; since 2.30.0 it is answered
`-32601` and leaves only the `front_door_tool_call` line with
`outcome=not_found` that any name the caller cannot call leaves, and the drift
is recorded once. A count of mismatch events per call from an older gateway is not comparable with one from
a newer one. With `pin_recheck_interval_s: 0`, a drift was on record only when
someone called the tool.

**Before 2.31.0, an `expired` approval on a stdio gateway says nothing about
what an approver would have decided.** Nobody could decide it: a stdio gateway
serves no REST API, and nothing else resolved a held call, so a call on an
`approval_list` there could only time out
([mcp-hangar#1929](https://github.com/mcp-hangar/mcp-hangar/pull/1929)). A
2.30.x stdio gateway's record has this gap too.

## What a record from before 2.25.0 lacks

The same rule again: an export from a 2.24.x or earlier gateway has the older
behaviour, whatever the rows above now say.

**An `approved` record does not establish that the call could run.** An
approval that arrived after its call's batch deadline was accepted with `200`,
recorded `approved` and published as `ToolApprovalGranted` with the approver in
`decided_by`, although the call was never dispatched
([mcp-hangar#1702](https://github.com/mcp-hangar/mcp-hangar/issues/1702)).

**An auth event does not establish who made the change.** `created_by`,
`revoked_by`, `assigned_by` and `updated_by` came from the request body and
defaulted to `"system"`, so an admin could mint a key or grant a role and have
the event, the log line and the response name someone else
([mcp-hangar#1649](https://github.com/mcp-hangar/mcp-hangar/issues/1649)).

**A gateway that booted may have had no policy for a scope.** A `tools:` or
`access:` policy with one invalid field was dropped with an
`invalid_tools_access_config` warning, and a list written as a string was read
as its characters -- `deny_list: add` allowed `add`
([mcp-hangar#1648](https://github.com/mcp-hangar/mcp-hangar/issues/1648),
[mcp-hangar#1718](https://github.com/mcp-hangar/mcp-hangar/issues/1718)). A tool
call it served is not evidence that the written policy allowed it; read its
boot log for that warning.

**A pin did not see unannounced drift.** The catalogue a pin was checked against
was refreshed only at start and on `tools/list_changed`, so a passing pin there
says the tool matched what the server served when it last started
([mcp-hangar#1693](https://github.com/mcp-hangar/mcp-hangar/issues/1693)).

**A pin did not see a tool beyond the first page.** An upstream that paginated
`tools/list` was read to its first page only, so a tool on a later page was not
listed, not pinned, not checked for drift (the periodic re-check included) and
could not be called through Hangar. Fixed in 2.28.0
([mcp-hangar#1874](https://github.com/mcp-hangar/mcp-hangar/pull/1874)).

**A SIEM export may be missing records without saying so.** An unknown
`MCP_COMPLIANCE_FORMAT` started the gateway with no export, and a record that
could not be written was dropped with an error log line and no metric
([mcp-hangar#1701](https://github.com/mcp-hangar/mcp-hangar/issues/1701)). Since
2.25.0 the first refuses startup and the second is counted in
`mcp_hangar_compliance_export_failures_total`.

## What a record from before 2.24.0 lacks

The same rule as the next section: a record does not improve when the code
does. An export from a 2.23.x or earlier gateway has the older behaviour.

**A refusal is in no audit export.** The OTLP audit exporter and the compliance
formats wrote successes and upstream failures only. A refusal appeared in the
log and, for some, as a domain event of its own -- `EgressPolicyEnforced`,
`ToolApprovalDenied`, `AuthorizationDenied` -- which neither exported. Its
absence from an export is not evidence that nothing was refused.

**A group call's record names the member**, not the group, and **no record names
a role**: `mcp.caller.roles` was defined and never written.

**A front-door call did not establish `tool:invoke`.** The flat `tools/call`
never checked it, so with auth on a principal without it -- one holding only
`viewer`, for example -- was served what `hangar_call` refused it
([mcp-hangar#1623](https://github.com/mcp-hangar/mcp-hangar/pull/1623)).

**A header verdict on `hangar_call` did not establish validation.** Every
`Mcp-Param-*` header on a modern request was handed to the policy as validated,
including on `hangar_call`, where nothing checks it against the body, and a
header mapping that did not state validation was read as validated
([mcp-hangar#1598](https://github.com/mcp-hangar/mcp-hangar/pull/1598),
[mcp-hangar#1601](https://github.com/mcp-hangar/mcp-hangar/pull/1601)). An
earlier gateway's `rule_kind=header` verdict on `hangar_call` says a header
matched, and nothing about whether the header was true.

**Spans carried the caller's ids by default** -- `mcp.caller.id`, `mcp.user.id`,
`mcp.agent.id` and `mcp.session.id` on every authenticated call -- and **no span
named the L7 verdict or the member a group call went to**.

## Three rows that were weaker before 2.16.0

This page was drafted against 2.15.0, where three of its rows read worse. They
are kept here because a record does not improve when the code does: anyone
holding an export from a 2.15.0 or earlier gateway -- or still running one --
has the older behaviour, whatever this page says about the current release.

**An enforced deny left almost no record.** Audit mode — the mode that by
definition changes nothing — emitted an event, a warning and a metric, while
Enforce mode emitted a `debug`-level line carrying the generic caller-facing
message, with the reason the policy computed left in `.details` where only the
REST middleware looked. Fixed in
[mcp-hangar#1128](https://github.com/mcp-hangar/mcp-hangar/pull/1136): a refusal
now publishes `EgressPolicyEnforced`, increments its own counter and logs at
warning, **since 2.16.0**. **A refusal by an earlier gateway is in no event
stream at all** — its absence from an export is not evidence that nothing was
refused.

**No verdict named its policy.** `PolicyEvaluationResult.policy_id` was
documented as "the policy that made the decision (for audit)" and was never set
by anything; the nearest answer was a timestamp join against `EgressPolicySet`,
which is a reconstruction rather than a record. Fixed in
[mcp-hangar#1129](https://github.com/mcp-hangar/mcp-hangar/pull/1135), released
in 2.16.0: every L7 verdict carries a content hash of the rules that produced it,
and the unfilled field is gone. **A verdict from an earlier gateway names no
policy**, and the timestamp join is the only reconstruction available for it.

**The approval copy leaked a nested secret.** Argument redaction matched
sensitive key names at the top level only, so `{"config": {"password": …}}` — and
the same key inside a list of records — was persisted and served verbatim to
every `approval:read` holder. Fixed in
[mcp-hangar#1130](https://github.com/mcp-hangar/mcp-hangar/pull/1134), released
in 2.16.0. **An approval record written by an earlier gateway may contain a
secret**, and the integrity hash is unaffected either way: it is computed over
the raw arguments by design.

## How to read a record you did not produce

1. **Find the reason, not only the outcome.** Every verdict above carries one.
   A record with an outcome and no reason is a log line, not a verdict.
2. **Find the rule.** For an L7 verdict that is `policy_id`; for a digest verdict
   the pinned digest; for tool access the policy scope in the operator-side log.
3. **Read the middle column before concluding anything.** Most of the wrong
   conclusions available here are of the form "it did not happen because I have
   no record of it" — and the middle column is where this page says which records
   do not exist.

## References

- [ADR-013 — egress policy enforcement model](../adr/ADR-013-egress-policy-enforcement-model.md)
- [ADR-025 — a header selector must not match an unvalidated header](../adr/ADR-025-header-selectors-must-not-match-unvalidated-headers.md)
- [operations/COMPLIANCE_POSTURE.md](../operations/COMPLIANCE_POSTURE.md) — the same shape at the certification layer
- [operations/COMPLIANCE.md](../operations/COMPLIANCE.md) — SIEM export formats
- [security/OWASP_MCP_TOP_10_COVERAGE.md](./OWASP_MCP_TOP_10_COVERAGE.md) — the same controls, per OWASP category
