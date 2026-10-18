# Tool-result surfaces

Every place MCP Hangar reads or rewrites the result of a tool call, as of core 2.29.0 plus the changes merged after it. The inventory exists because the Core Primitives working group is expected to redesign the `tools/call` result (`content` and `structuredContent` can carry the same output twice, and implementations diverge; SEP-3279 is one candidate shape). When a shape lands, every path below moves at once, and a path missing from this list is the one that breaks.

Paths are `file:function` under `src/mcp_hangar/` in the core repository. "Test" names a test that exercises the path; "untested" means no test was found that drives the behaviour described, which is a gap, not a statement that it works.

## The result's path, in order

1. [Upstream response read](#1-upstream-response-read)
2. [The aggregate's reading of the answer](#2-the-aggregates-reading-of-the-answer)
3. [Response mutators](#3-response-mutators)
4. [Batch truncation and continuation](#4-batch-truncation-and-continuation)
5. [`hangar_call` packing](#5-hangar_call-packing)
6. [Front-door flat return](#6-front-door-flat-return)
7. [`resource_link` projection](#7-resource_link-projection)
8. [Task results](#8-task-results)
9. [`isError` handling](#9-iserror-handling)
10. [Redaction in events, audit and logs](#10-redaction-in-events-audit-and-logs)
11. [Digest pinning and `outputSchema`](#11-digest-pinning-and-outputschema)
12. [Audit and SIEM export](#12-audit-and-siem-export)

## 1. Upstream response read

- **Where:** `http_client.py` (the bounded body reader that raises `ResponseTooLarge`), read through `domain/model/mcp_server.py:McpServer.invoke_tool`.
- **Reads:** the upstream's response body, up to `execution.max_response_bytes` (per server override available).
- **Writes:** nothing. A body over the limit fails the call before it is held.
- **Test:** `tests/integration/test_an_oversized_upstream_response_reads_the_same_on_every_surface.py`.

## 2. The aggregate's reading of the answer

- **Where:** `domain/model/mcp_server.py:McpServer.invoke_tool`.
- **Reads:** the JSON-RPC response. An `error` member becomes a `ToolInvocationError` (`tool_error: <message>`, with the JSON-RPC code in `details`). A `result` with `isError: true` is a failure too: the text of its content blocks becomes the message and the `ToolInvocationFailed` event's `error_message`, and the whole result is kept in `details.result` (since #1900). A `result` otherwise is a success.
- **Writes:** `ToolInvocationCompleted(result_size_bytes=len(str(result)))` or `ToolInvocationFailed`; the success result is returned as received.
- **Test:** the `is_error` and `rpc_error` canary tools (`tests/integration/_canary_upstream.py`, `_canary_harness.py`); `tests/integration/test_an_upstreams_failure_envelopes_reach_the_caller_unchanged.py`.

## 3. Response mutators

- **Where:** `server/tools/batch/executor.py:BatchExecutor._mutate`, called with `("tools/call", "response", result, call_id)` after a successful invoke.
- **Reads/writes:** the interceptor `MutatorPipeline` receives the upstream result dict itself as the payload and may return a different one. The default pipeline is empty and changes nothing. A failure result never reaches it.
- **Observation:** the built-in `application/mutators/response_truncator.py:ResponseTruncator` reads `payload["result"]`, a key the executor's payload (the result dict, with `content`, `structuredContent`, `_meta`) does not have, so on the executor's payload it changes nothing. It is not registered anywhere in `src`; only tests construct it. A redesign should decide whether the payload shape is the result or a wrapper around it.
- **Test:** `tests/unit/test_mutator_wiring.py`, `test_mutator_pipeline.py`, `test_response_truncator.py` (the truncator against a wrapper payload, not the executor's), `test_payload_shaping_is_traced.py`.

## 4. Batch truncation and continuation

- **Where:** `server/tools/batch/executor.py:BatchExecutor._apply_batch_truncation`, then `infrastructure/truncation/manager.py:TruncationManager.process_batch`, `_truncate_result`, `_smart_truncate_json`, `_truncate_dict`.
- **Reads:** `CallResult.result` of every budgeted call in a `hangar_call` batch. A failure (`result is None`) is left alone.
- **Writes:** over the batch budget, a structure-preserving cut of `result` (keys kept, values cut, so a `_meta` or `structuredContent` value can be cut like any other), the flags `truncated`, `truncated_reason`, `original_size_bytes`, and a `continuation_id`. The full result is stored under the calling identity.
- **Not applied to:** a call whose caller takes the result whole (`CallSpec.whole_result`): the front-door flat call and the facade's `invoke`.
- **Continuation read:** `server/tools/continuation.py:hangar_fetch_continuation` returns the stored result in byte slices to the identity it was stored for, and `hangar_delete_continuation` frees it.
- **Test:** `tests/unit/test_truncation.py`, `test_a_continuation_is_confined_to_its_owner.py`, `tests/integration/test_a_front_door_flat_call_takes_its_result_whole.py`, `tests/live/test_t2_continuation_owner.py`. Cutting a result that carries `_meta` or `structuredContent`: untested.

## 5. `hangar_call` packing

- **Where:** `server/tools/batch/executor.py:format_result_dict`, returned by the `hangar_call` tool in `server/tools/batch/__init__.py`.
- **Reads:** `CallResult`.
- **Writes:** one entry per call: `index`, `call_id`, `success`, `result`, `error`, `error_type`, `elapsed_ms`, and when set `truncated*`, `continuation_id`, `retry_metadata`, `upstream_result` (a failure the upstream reported, since #1900). The batch dict then leaves through FastMCP's tool conversion, which serializes it twice: as a JSON text block and as `structuredContent`. This is the duplicated output the working group describes, produced by Hangar for its own tools.
- **Test:** `tests/integration/test_a_front_door_flat_call_takes_its_result_whole.py` (`_batch_entry`), `tests/integration/test_an_upstreams_failure_envelopes_reach_the_caller_unchanged.py`.

## 6. Front-door flat return

- **Where:** `fastmcp_server/flat_tool_projection.py:_flat_call_tool` (inside `register_flat_tool_handlers`), `_failed_flat_result`, `fastmcp_server/flat_call_tasks.py:govern_flat_call`.
- **Reads:** the one `CallResult` of a single-call batch run through the same executor and gates as `hangar_call`.
- **Writes:** on success, the raw result dict, which the lowlevel handler wraps (the result is whole since 2.24.0, #1611). On failure, the upstream's own failure result when it reported one (#1900), otherwise `isError: true` with Hangar's error text. A task the upstream created is answered with its SEP-2663 task result.
- **Test:** `tests/integration/test_a_front_door_flat_call_takes_its_result_whole.py`, `tests/unit/test_flat_tool_reexport.py`, `tests/integration/test_an_upstreams_failure_envelopes_reach_the_caller_unchanged.py`.

## 7. `resource_link` projection

- **Where:** `fastmcp_server/resource_link_read_through.py:project_result_uris`, called from the flat call, from `fastmcp_server/prompt_proxy.py` for `prompts/get`, and from `fastmcp_server/task_relay_handlers.py` for relayed task results.
- **Reads:** the whole result, walking every nested node (not only `content`).
- **Writes:** in place, every `resource_link` `uri` and embedded resource `uri` is namespaced with the owning upstream; handed-out links are remembered per tenant. A no-op outside `front_door`.
- **Test:** `tests/unit/test_a_handed_out_resource_link_is_resolvable.py`, `tests/unit/test_an_upstreams_resources_are_served_through_the_front_door.py`. A `structuredContent` that contains a node shaped like a `resource_link`: untested.

## 8. Task results

- **Where:** `server/tools/batch/relay_seam.py` (reads an upstream task handle in either shape), `fastmcp_server/task_relay_handlers.py` (serves `tasks/*` follow-ups).
- **Reads:** an upstream result that is a task handle (flat `resultType: "task"`, or nested `task`).
- **Writes:** the ledger entry takes the handle's fields without `resultType` and `_meta`; field names are mapped to the ledger's (`ttlMs` to `ttl`, `pollIntervalMs` to `pollInterval`). The handle given to the client is rebuilt as a SEP-2663 task result, so an upstream's `_meta` on a task handle does not reach the client.
- **Test:** `tests/unit/test_a_task_a_flat_call_created_can_be_polled.py`, `test_task_follow_ups_link_to_origin.py`. `_meta` on a handle: untested.

## 9. `isError` handling

- **Where:** `domain/model/mcp_server.py:McpServer.invoke_tool` (turns `isError` into a failure); `fastmcp_server/tool_error_flag.py:flag_tool_errors` (sets `isError: true` on the wire for a `hangar_*` tool's error payload, #1669); `server/tools/batch/member_health.py` (an `isError` result counts as the member answering, not as a broken member); `observability/tracing.py` and `fastmcp_server/flat_call_log.py` (the span outcome and the call log line read `isError`).
- **Reads:** the `isError` member of a result, and the three-key error payload of a `hangar_*` tool.
- **Writes:** `isError` on a `hangar_*` result only; an upstream's result is never relabelled.
- **Test:** `tests/unit/test_a_tool_error_payload_is_flagged_on_the_wire.py`, the canary `is_error` tool.

## 10. Redaction in events, audit and logs

- **Where:** `domain/security/argument_redaction.py:redact_arguments` and `hash_arguments` (request arguments, in invocation events, approvals and a server's recorded env); `logging_config.py` (the structlog processors that scrub and bound every log field); `redactor.py:OutputRedactor` (a server's stderr lines and load-error reasons).
- **Reads/writes:** arguments and log fields. **No path redacts a tool result.** Events carry `result_size_bytes`, never the result. The one route by which result text reaches an event is `ToolInvocationFailed.error_message`, which holds the text of an `isError` result's content blocks; `application/event_handlers/security_handler.py` deliberately leaves it out, and `alert_handler.py` forwards it.
- **Test:** `tests/unit/test_tool_arguments_are_redacted_on_every_exit.py`, `test_approval_argument_redaction.py`, `test_log_redaction.py`, `test_output_redactor.py`. Redaction of `error_message` in the alert path: untested.

## 11. Digest pinning and `outputSchema`

- **Where:** `domain/services/digest_computation.py` (the digest covers `name`, `description`, `inputSchema`, `outputSchema`), `domain/model/tool_catalog.py` (carries `output_schema`), `fastmcp_server/flat_tool_projection.py` (the digest on a listing).
- **Reads:** the tool definition of a listing.
- **Writes:** nothing on a result. A search of `src` finds no code that validates a result against its `outputSchema`; the schema is pinned and listed, and a result's `structuredContent` is relayed without being checked against it.
- **Test:** `tests/unit/domain/services/test_digest_computation.py`, `tests/unit/test_digest_pinning.py`, `tests/integration/test_a_tools_digest_reads_on_hangar_tools_and_rest.py`. Result against `outputSchema`: not implemented, so nothing to test.

## 12. Audit and SIEM export

- **Where:** `compliance/cef_formatter.py`, `compliance/cef_exporter.py`, `compliance/leef_exporter.py`, `compliance/jsonlines_exporter.py`, fed by `application/event_handlers/audit_handler.py`.
- **Reads:** audit records built from domain events.
- **Writes:** event fields only. A result body is not an event field, so none is exported; a failed call's bounded `error_type` is.
- **Test:** `tests/unit/test_compliance_exporters.py`, `tests/unit/test_export_formats.py`.

## Findings for the redesign

- The `ResponseTruncator` mutator does not match the payload the executor gives mutators (section 3).
- Batch truncation can cut `_meta` and `structuredContent` values independently of `content` (section 4); no test pins what a client then sees.
- An upstream's `_meta` on a task handle is dropped (section 8).
- Result text reaches alerts through `error_message` without the redaction that arguments get (section 10).
- `hangar_call` serializes its own batch result twice (section 5).
