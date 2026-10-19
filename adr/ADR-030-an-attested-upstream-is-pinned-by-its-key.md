# ADR-030: An Attested Upstream Is Pinned by Its Key at the Connection, Not Labelled in the Verdict

**Status:** Proposed
**Date:** 2026-10-19
**Authors:** MCP Hangar Team

## Context

State of `main` on 2026-10-19: core 2.31.0 (`40f448a1`), operator `6d5d7e6` with CRD `v1alpha2`. Every claim below names a path.

**Hangar already proves the integrity of a tool's contract, and nothing about the code behind it.** The JCS digest over `{name, description, inputSchema, outputSchema}` ([ADR-004](ADR-004-sep-1766-digest-pinning.md), `domain/services/digest_validator.py`) is enforced by `_gate_digest_pin` and `_gate_deferred_digest_pin` (`server/tools/batch/executor.py:2234`, `_GATES` at `:3104-3117`). Since 2.28.0 (#1802) a pin is bound to `McpServer.upstream_identity()` (`domain/model/mcp_server.py:578-597`) and the binding is checked at call time (`executor.py:473-476`, `digest_validator.py:77`). Pin history lives in the `pin_ledger:<server>` stream as `ToolPinRecorded`, a log derived from configuration (`domain/events/enforcement.py:351-357`), not the other way round.

**For every operator-managed server, `upstream_identity()` is a pod IP and port, not an image.** The operator annotates the pod (`operator/pkg/provider/builder.go:192-195`: `mcp-hangar.io/enabled|name|mode=http|port`); core discovers it from `pod.status.pod_ip` (`infrastructure/discovery/kubernetes_source.py:250-287`) and registers it as `mode: remote`, so the identity is `remote:http://<pod_ip>:<port>`. The `image:` branch of `upstream_identity()` serves Hangar's own Docker mode only. Core never learns the image digest of an operator pod. Any design that binds an attestation fact to `upstream_identity()` for operator pods is binding it to an IP the CNI will reuse.

**Nothing in the code attests a workload.** A grep of `src/`, `api/`, `internal/` and `docs/adr/` for `attest|TEE|enclave|SPIFFE|trustee|SEV-SNP|TDX|RATS|EAT|runtimeClass` returns only: build provenance of Hangar's own artefacts (`actions/attest-build-provenance@v4` in core `release.yml:232`; `cosign sign`/`cosign attest` for SBOM and SLSA in the operator and chart release workflows; `tests/ci/test_a_release_carries_verifiable_artifacts.py`); the phrase "either client-attested or \"unknown\"" in `approvals/api/routes.py:257-258`, where attested means self-asserted; and `docs/operations/COMPLIANCE_POSTURE.md`, which says Hangar is not an attestation in the SOC 2 sense.

**The operator cannot place an upstream in a Confidential Container.** `MCPServerSpec` (`operator/api/v1alpha2/mcpserver_types.go`) passes `nodeSelector`, `tolerations`, `affinity`, `priorityClassName`, `serviceAccountName`, `automountServiceAccountToken`, `podSecurityContext` and `imagePullSecrets` into the PodSpec (`pkg/provider/builder.go:83-107`); there is no `runtimeClassName` anywhere in `api/`, `pkg/`, `internal/` or `config/`. Without `runtimeClassName: kata-qemu-snp|kata-qemu-tdx` the pod does not start in a confidential VM. This gap exists independently of attestation (gVisor and plain Kata need the same field).

**The HTTP client already pins a CA per upstream.** `infrastructure/launchers/http.py:35-51,172-212` accepts `tls.ca_cert_path` from the server's `tls` block (`server/config.py:1279`) and warns (`tls_verification_disabled`), naming `tls.ca_cert_path`, on the `verify_ssl: false` + no-CA combination; it does not refuse it. The CRD has no TLS block; operator pods are discovered as plain `http`.

**Image integrity is already an admission policy.** `operator/config/admissionpolicy/image_digest.yaml` + `params.yaml` give `imageDigestPolicy: off|warn|block` (default `warn`) as a ValidatingAdmissionPolicy; `internal/webhook/image_digest.go:9-21` (`IsImageDigestPinned`) is the controller's egress coupling plus a VAP mirror — the webhook copies are gone (#312). Intra-object consistency rules in this CRD family are expressed as CEL `XValidation` on the type (`api/v1alpha2/mcpdiscoverysource_types.go:31-32,47`). An `MCPEgressPolicy` upstream match (`UpstreamMatch`) carries `toolSchemaDigestRef` and an `imageDigest` mode, `required|inherited` (`mcpegresspolicy_types.go:103-119`).

**Other primitives that matter, as they are.** `HandlerKind` (`domain/contracts/event_bus.py:13-68`): `PROJECTION` runs on every replica for every event, must be built from the event payload and must not publish; `EFFECT` touches the world and runs only on the producing instance; `McpServerStarted` is produced by every replica, because each starts its servers itself (`event_bus.py:60-66`, [ADR-020](ADR-020-high-availability.md) "what stays local"). The fleet snapshot (`domain/services/fleet_snapshot.py:113-125`) is configuration: a server rebuilt from it starts `COLD`, and `enforce_ssrf` is derived, not trusted on read (`:70-110`). OPA authorization for `hangar_call` runs per call before `BatchExecutor.execute` with no context filled (`server/tools/batch/__init__.py:245`; [ADR-028](ADR-028-the-front-door-invoke-gate-is-the-tool-access-policy.md) §2). The operator delivers L7 policy through `POST /api/mcp_servers/{id}/l7_policy` (`server/api/mcp_servers.py:526-528`, operator `pkg/hangar/client.go:397-401`) under the `kubernetes-operator` role, which holds `policy:write` (`auth/roles.py:176-195`). [ADR-029](ADR-029-one-enrichment-boundary-and-a-bounded-decision-vocabulary.md) gives `hangar.gate.decision` span events with a bounded `hangar.gate.reason` (`observability/conventions.py:145-170`); `mcp-hangar why` (2.28.0) reads refusals from the event store.

**External forces.** Attestation of MCP servers is being named as a gap by the confidential-computing community, and TEE-hosted MCP gateways now position themselves against software-only governance: a policy engine inside a TEE with its policy hash in the attestation report, without a fleet, Kubernetes or contract digests. Research on MCP security shows that an MCP server an intermediary cannot authenticate is easy to impersonate.

**Boundaries this record does not move.** Deterministic enforcement, no ML; no SaaS ([ADR-010](ADR-010-retire-agent-cloud-tier.md)); L7 egress with a network backstop and no MITM/eBPF ([ADR-013](ADR-013-egress-policy-enforcement-model.md)); in-cluster MITM outside the threat model; the event log signed by the operator's key (the circular trust named in docs#252) stays as it is.

**The question.** Whether, where and in what form the fact "this upstream runs attested code" enters Hangar's behaviour — and what Hangar must refuse to become in the process.

## Decision

When an operator declares an upstream `tls.attested: true`, Hangar requires every connection that carries a call to that upstream to terminate at a key whose SPKI digest is in the operator's pin list — keys the operator obtained from a Key Broker Service that releases them only to attested guests — verified after the handshake and before the first byte, and recorded in the audit trail from the socket. Hangar does not verify evidence, trust a CA, issue nonces, or become a subject of attestation, and "attested" means attestation-gated issuance (Guarantee A), never continuous runtime attestation (Guarantee B).

### 1. Two independent policy enforcement points; Hangar is the first and only the first

Hangar answers `allow(principal, tenant, tool, args)`. A Key Broker Service (Trustee KBS or equivalent) answers `release(secret, measurement, nonce, pubkey, policy)` to an attested guest. Neither replaces the other: a Hangar refusal means the call never reaches the upstream; a KBS refusal means the upstream has nothing to execute it with. Hangar does not hold downstream secrets, does not release keys and does not become a KBS.

### 2. The attestation-derived fact Hangar consumes is the public key at the other end of the connection

An attested upstream terminates TLS with a per-workload leaf key that the KBS released to that guest after attestation. Hangar pins the SPKI digest of that key (`peer_identity.spki_sha256`, a list to allow rotation windows). No CA is a trust input for an attested server: a CA private key released to a guest would let any admitted guest mint a certificate for any name, a CA kept at the issuer still makes the SAN a statement of issuance policy Hangar cannot see, and hostname matching in the client accepts DNS/IP SANs only, so a SPIFFE URI SAN would not survive the handshake and a static leaf cannot carry a CNI-assigned pod IP. Pinning the key removes all three problems: the chain is irrelevant (a self-signed leaf is fine), the name is irrelevant, and what Hangar records is *this connection terminated at key K, which the operator obtained from the KBS resource provisioned for this workload*. That resource is named in the declaration as `peer_identity.key_ref` (for example the KBS resource path), a stable name for the key lineage that does not change when the key rotates (§7). The binding holds for the life of the connection; Hangar does no TTL, nonce or replay reasoning.

Two guarantees are kept apart and this record provides only the first. **Guarantee A — attestation-gated credential issuance:** key K was released under a policy that required a successful attestation of the guest for the workload K was provisioned for. **Guarantee B — continuous runtime attestation:** the process answering now is in a verified TEE state. TLS proves possession of K, not where K lives today: a key exfiltrated from a compromised guest, or a guest whose measurement drifted after release, still completes the handshake. A revocation at the KBS does not reach Hangar: a key stays acceptable to Hangar for as long as it is in the pin list, whatever the KBS has since decided. The issuer-side mitigations are short-lived keys and re-release tied to re-attestation; the Hangar-side control is the pin list itself. Changing the pin list replaces the server's HTTP client on the replica that applies the change: a new connection pool is built against the new list and the old pool is drained (an in-flight request finishes; the streamable-HTTP GET stream is closed and re-opened on the new pool). Every replica must apply the change, including one that already holds the server. The fleet projection builds a peer's copy of a server only when the peer does not yet hold it (`application/event_handlers/fleet_projection.py:126-130`, [ADR-020](ADR-020-high-availability.md)), so this record requires a path by which a pin-list change on one replica is applied on the others; a replica that has not applied it still accepts the old list. `tls.max_connection_age` (default 1 h) caps the life of any single connection, so a long-lived connection is re-checked against its replica's current list; it does not bound a replica that has not yet received the change. Exposure to a key that should no longer be trusted is therefore bounded by the time until the operator removes it from the pin list and that change reaches every replica, not by anything the KBS does.

### 3. Hangar is a relying party only through TLS; it is not a verifier

Hangar does not parse or verify Evidence, does not talk to an Attestation Service, holds no Endorsements or Reference Values, ships no attestation client, and does not evaluate X.509 chains for attested servers. The SPKI digest is computed with the `cryptography` package already in the dependency set (`pyproject.toml:70`). The domain stays free of platform SDKs.

### 4. Declaration and its carriage

**Config file.** The `tls` block gains `peer_identity` and `attested`:

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: https://10.244.3.17:8443          # pod IP, Service name, anything: the name is not checked
    tls:
      attested: true
      peer_identity:
        key_ref: kbs:///default/payments/tls-key     # stable name of the key lineage; survives rotation
        spki_sha256:
          - sha256:9f2c...                     # current KBS-released key
          - sha256:4b10...                     # next key during rotation
      max_connection_age: 1h
```

Load-time refusals (`ConfigurationError` naming both halves, the #841/#902 pattern): `attested: true` on `mode: subprocess` or Hangar's own container mode (no connection to bind); with an `http://` endpoint; with an empty `spki_sha256` list or no `key_ref`; with `verify_ssl: false` (meaningless, but a sign of a misread). `ca_cert_path` may be present for non-attested servers and is ignored for attested ones with a warning.

**CRD.** `MCPServerSpec` gains `runtimeClassName` (container mode; passed into the PodSpec in `pkg/provider/builder.go`) and `tls: {attested, peerIdentity: {keyRef, spkiSha256: []}, maxConnectionAge}`. SPKI digests are public values, so no Secret or ConfigMap reference is needed and the operator's least-privilege RBAC (`rbac_least_privilege_test.go:22-33`: no Secret reads) is untouched. CEL `XValidation` (`mcpdiscoverysource_types.go:31-32` precedent): `tls.attested == true && mode == 'container'` requires `runtimeClassName`; `tls.attested == true` requires a non-empty `spkiSha256` and a `keyRef`. Remote-mode CRs need no runtime class. `runtimeClassName` is an operational precondition, not evidence: `gvisor` satisfies the rule and attests nothing. The image-digest admission policy refuses the per-object opt-out `hangar.io/allow-mutable-image` (`image_digest.yaml:35-36`) on an attested CR.

**Carriage: operator to core is the only declaration path, and it does not exist today for container mode.** The operator registers only remote-mode CRs with core (`internal/controller/mcpserver_registration.go:222-224`, body `{mcp_server_id, mode, endpoint}`, `pkg/hangar/client.go:485`); container-mode pods reach core solely through core's own annotation discovery, which hardcodes `http://` (`server/bootstrap/discovery.py:235`) and skips unknown modes (`:186-196`); the REST create route reads no `tls` (`server/api/mcp_servers.py:319-360`) and `CreateMcpServerCommand` has no such field. This record therefore requires:

- (a) the operator registers container-mode CRs with `tls.attested` by POST too, with the pod's endpoint and the `tls` block;
- (b) the REST create/update body, `CreateMcpServerCommand` and `UpdateMcpServerCommand` gain a `tls` field, and the update gains `endpoint` so a rescheduled pod can be re-pointed; both require `mcp_servers:attest` (§9). An endpoint created over REST is a HUMAN-provenance endpoint under the SSRF policy (ADR-021), so the pod CIDR must be in `ssrf.trusted_networks`;
- (c) the operator emits no discovery annotations for an attested CR, and core discovery never creates, replaces or downgrades a server whose name the operator has registered or that is declared attested. The refusal (`discovered_attested_upstream_without_tls`) is keyed on core state, not on an annotation the pod sets for itself. Because a pod observed before the operator's registration could still land first as plain `http`, the operator's registration replaces a server whose provenance is DISCOVERY;
- (d) `MCPDiscoverySource` sources with an attested `providerTemplate` are refused by the CEL for the source: the template is deep-copied into every server the source yields (`mcpdiscoverysource_controller.go:751-753`), so they would all share one `keyRef` and one pin list, which §7 forbids;
- (e) the operator registers an attested CR only with a core that advertises the capability, and otherwise reports the CR as not ready. A core that does not know the field would ignore `tls` in the REST body (`server/api/mcp_servers.py:342-360`), and its launcher reads only `verify_ssl` and `ca_cert_path` (`launchers/http.py:176-182`), so an attested declaration on an older core would be silently served as a plain one. A configuration file that sets `attested` therefore requires a core that knows the key; the upgrade note says so.

**Integrity of the declaration.** The SPKI list travels operator to core over `hangar.url` with `X-API-Key` (`pkg/hangar/client.go:582-583`), whose documented example is plaintext (`helm-charts/.../values.yaml:177-180`). The declaration is public data; its integrity is what matters, and it is protected exactly as far as that channel is. An attested declaration is only as trustworthy as the operator-to-core channel, and the Helm defaults for attested deployments set `hangar.url` to `https://`, with the core's certificate verified against `hangar.tls.ca`. Delivery of the pin list to core is therefore inside the trust model; delivery of calls to the pod is not.

### 5. Enforcement at connect, before the first byte, fail-closed

For a server with `tls.attested: true`, the client builds an `ssl.SSLContext` with `check_hostname=False` and `verify_mode=CERT_NONE` for chain purposes, and the check runs inside that context's TLS handshake: the context's `sslsocket_class` and `sslobject_class` complete the handshake, read the peer certificate (`getpeercert(binary_form=True)`, which returns the DER certificate under `CERT_NONE`), hash its SPKI and raise when the digest is not in the pin list. The connection is therefore refused before the HTTP library returns it to the pool and before any request byte is written; httpx itself offers no hook between handshake and first write. The exception types do not derive from `OSError`, because httpcore maps an `OSError` raised during `start_tls` to `ConnectError` and the type would be lost. This is new TLS verification code in the transport (`http_client.py:425-495` area), merged with `_SsrfGuardedTransport` so there is one transport, and it applies to every new connection including retries, reconnects and pool replacement.

A mismatch fails closed — no fallback to standard HTTPS verification, no plaintext — with one bounded code per case: `attested_upstream_key_mismatch` (the key is not in the list), `attested_upstream_plaintext` (the peer did not speak TLS) and `attested_upstream_handshake_failed` (any other handshake failure). The transport raises a dedicated exception type for each.

Today three layers convert every exception on the start path, and each must let these types through: `HttpClient.call` wraps any exception in `ClientError("request_failed")` and must re-raise them; `McpServer` start wraps any exception in `McpServerStartError` (`mcp_server.py:969-985`) and must re-raise them unwrapped, as it already re-raises `McpServerNotHereError` (`:951-961`), still recording the failure with `_handle_start_failure` as that branch does; `_gate_cold_start` refuses any exception with the literal error type `McpServerStartError` (`executor.py:2553-2557`) and needs an explicit `except` that refuses with the type's own name. `_GATE_REASONS` is keyed by the refusal's `error_type` string, which the gate sets (`executor.py:2908-2911`); the three new types map to the three codes with outcome `deny`, not `error`: refusing a peer that is not the declared one is a decision, not broken machinery. ADR-029 §5 already requires a bounded code list per gate, defined next to the gate; adding these codes extends that list and does not amend ADR-029.

On a `COLD` or `DEAD` server the first contact happens in `_gate_cold_start` (`executor.py:2512`), which records the gate decision with the specific reason and publishes the `ToolCallRefused` that every gate refusal publishes; on a warm server the failure is a `ToolInvocationFailed` with `failure_code` set. A mismatch counts as a failed start for backoff and the circuit breaker, like any failed start; the refusals that follow it keep their own reasons (`not_revived_by_calls`, `circuit_open`), and the server's last start error is the mismatch. No new entry in `_GATES`.

### 6. Audit, from the socket, with explicit semantics

`ToolInvocationCompleted` and `ToolInvocationFailed` gain optional `upstream_peer_spki: str | None`; `ToolInvocationFailed` gains `failure_code: str`; and `ToolInvocationFailed` and `ToolCallRefused` gain `observed_peer_spki` for `attested_upstream_key_mismatch`, so the observed key is kept on the cold-start path too. The value is read from the connection that served this attempt (`response.extensions["network_stream"].get_extra_info("ssl_object")`), never from configuration, so a retry on a different connection records that connection's key and a group member's key is never attributed to a call another member served.

| Case | `upstream_peer_spki` | Other fields |
| --- | --- | --- |
| Refusal before any connection | absent | — |
| Handshake failure or plaintext peer | absent | `failure_code` (or the refusal's reason) set |
| Key mismatch | absent | `observed_peer_spki` set |
| Verified connection, call succeeded or failed at the application level | the verified key | — |

Exporters JSON/CEF/LEEF/syslog carry the field next to `caller_id`; spans carry `hangar.upstream.peer_spki`. `mcp-hangar why` already reads the `ToolCallRefused` a cold-start refusal publishes; it is extended to read `ToolInvocationFailed` rows whose `failure_code` is in the attested set (`refusal_log.py:26-32` today lists five refusal types and no invocation failures), and prints expected pins and observed key for both. It does not synthesise a `ToolCallRefused` for a warm transport failure. Metric: `mcp_hangar_attested_upstream_connections_total{server, outcome}`, registered in `_register_all_metrics()` (#1059).

### 7. The upstream identity of an attested server is its key

`McpServer.upstream_identity()` returns `attested:<key_ref>` for a server with `tls.attested: true`, instead of `remote:<scheme>://<host>:<port>`. The identity must be computable from configuration alone, because the #1802 binding is checked in `_gate_digest_pin`, which runs before `_gate_cold_start` and therefore before any connection exists; and it must be the same on every replica. A value taken from the connection, or derived from the pin list, fails both: the list changes when the next key is added and again when the old one is dropped. `key_ref` is the operator's stable name for the key lineage, so a rescheduled attested pod with a new IP keeps its digest pins, and a key rotation keeps them too. Nothing is lost by not binding to the key itself: a key outside the pin list is refused at connect (§5) before any tool is served. Changing `key_ref` is a different upstream, and its pins are recorded again. Because `key_ref` is a label the declarer chooses, two rules keep it from carrying pins it should not: `key_ref` is unique across servers (a registration that reuses one is refused), and a pin-list update that shares no key with the previous list must change `key_ref` or is refused, so replacing the whole lineage of keys is never a rotation. Non-attested servers are unchanged.

### 8. What "attested" means in Hangar's vocabulary

`tls.attested: true` means: every connection to this server must terminate at a key whose SPKI is in the declared list, and the operator declares that those keys were released by a KBS only after attestation of the workload they were provisioned for (Guarantee A). Hangar verifies the key, not the attestation evidence. The declaration does not establish continuous runtime attestation, current measurements, code integrity, or protection against key extraction after release. Audit records distinguish the configured pins from the key observed on the connection; no observed key is recorded when no verified connection was established. Documentation keeps three things apart: build provenance of Hangar's artefacts; the digest of a tool's contract; the attested-issuance key of an upstream connection.

### 9. Permission and trust roots

Setting `tls.attested` or `peer_identity` over REST requires a new permission `mcp_servers:attest`, held by `kubernetes-operator` and `admin` only; `mcp_servers:write` alone (which `developer` holds, `auth/roles.py:197-203`) cannot declare a server attested or change its pins. Deleting a server last declared attested, or creating a server under its name, also requires `mcp_servers:attest`; otherwise a delete (which needs `mcp_servers:lifecycle`, `server/api/mcp_servers.py:419`, also held by `developer`) followed by a plain re-create under the same name would downgrade it without `mcp_servers:attest`. The config file remains operator-trusted ([ADR-021](ADR-021-config-file-endpoints-outside-the-ssrf-policy.md)).

Trust roots, named:

- (a) the KBS operator and its reference values;
- (b) whoever holds `mcp_servers:attest` or writes the config file — they can pin a key they control, so this is operator-declared trust, not independently administered trust, and the audit record says what the operator declared, not what a third party verified;
- (c) the guest TCB after key release — a compromised guest can exfiltrate K;
- (d) the operator-to-core channel for the integrity of the pin list (§4).

Independently administered trust (a core-side pin store the registrant cannot write) is a later decision and is not made here.

### 10. Defaults, compatibility, naming

No behavioural change for servers without `tls.attested: true`; existing TLS behaviour, including the `verify_ssl: false` warning (`launchers/http.py:196-210`), is untouched. The fleet snapshot carries no `tls` today (`snapshot_of`, `fleet_snapshot.py:38-76`; `server_from_snapshot`, `:140-170`): a server rebuilt from it on restart or on a peer replica would come back without `attested` and without pins and be served as a plain one. `McpServerConfigSnapshot` therefore gains the `tls` block (it holds no secret), `server_from_snapshot` restores it, and a row whose `tls.attested` cannot be restored is refused, not rebuilt as a plain server. Additive CRD fields, no API version bump. `McpServer.provenance` (`HUMAN | DISCOVERY`) keeps its SSRF meaning (ADR-021). Nothing here is named attestation result, measurement or verifier.

The change spans config and validation; a new transport verification path and its propagation through the start path; the registration body, command and REST fields; the fleet snapshot; the operator's container-mode registration and capability check; discovery refusal; event schema and exporters; `why`; one metric; one permission; the tests below.

## Consequences

### Positive

- A call to a declared server is carried by a connection that provably ends at one of the operator's pinned keys, verified before any byte is sent, and the audit record names the key read from the socket — a claim Hangar can stand behind, unlike a verifier result with a shelf life or a CA-anchored name whose meaning lives in an issuance policy Hangar cannot see.
- No new gate in `_GATES`, no new event type, no verifier client, no CA handling, no Secret reads in the operator. The trust root shrinks to "who may write the pin list".
- `runtimeClassName` closes a gap that exists regardless of attestation.
- Nothing changes for servers that do not declare `tls.attested: true`.

### Negative

- The KBS operator and its reference values are a trust root of Hangar's audit trail. A KBS policy that releases a leaf key to the wrong workload makes that server's "attested" records meaningless, and Hangar cannot detect it.
- Operator-declared trust only: whoever holds `mcp_servers:attest` or writes the config file can pin a key they control. The record names it and narrows it (`developer` cannot), but does not close it; independent administration is a later decision.
- Guarantee A, not B: a key exfiltrated from a compromised guest or a guest whose measurement drifted after release keeps working against Hangar until the operator removes it from the pin list; a revocation at the KBS alone changes nothing on Hangar's side. Documented; not solvable on Hangar's side without RA-TLS.
- The pin list's integrity depends on the operator-to-core channel; the Helm defaults for attested deployments must put `hangar.url` on TLS, and a deployment that does not is trusting its cluster network for that integrity.
- A declared server whose key is not in the list is unavailable, fail-closed, with no "temporary" plaintext mode. Rotation requires the operator to publish the next key before switching; a missed step takes the upstream down.
- Upstreams must serve TLS with the KBS-released key at start-up (CoCo CDH supports resource retrieval; serving TLS with it is integration work on the upstream image, outside Hangar).
- New operator work: POST registration of attested container-mode CRs; the discovery marker and refusal; `runtimeClassName`. New core work: transport verification, event fields, the fleet snapshot, `why`, permission, REST/command fields.
- Three things a reader will call "attestation" must stay apart in every document: build provenance of Hangar's artefacts, the digest of a tool contract, the attested-issuance key of an upstream connection.

### Neutral

- Nothing in this record needs hardware to implement or to test (a test CA, a test KBS or a static secret, `kata-qemu-coco-dev`), but no security statement may rest on a run without a TEE and the documentation must say so.
- The verifier-result design is rejected in the form described in Alternative 1; a design with a different binding would need its own record.
- Hangar-in-TEE (Alternative 5) remains possible as a separate record.

### What this decision does not establish

Row for `docs/security/VERDICT_LIMITS.md`:

| Verdict | Establishes | Does not establish | Operator |
| --- | --- | --- | --- |
| Verdict on a server declared `tls.attested: true` | The connection that carried this call terminated at a private key whose SPKI digest was in the operator's pin list at connect time; the operator declares that those keys were released by a KBS only after attestation of the workload they were provisioned for (Guarantee A). The observed key is recorded from the socket of the connection that served the attempt. | That the guest is now in a verified TEE state (Guarantee B); that the key has not been exfiltrated from the guest since release; that a key revoked at the KBS is refused while it is still in the pin list; that every replica has already applied the latest pin list; that the KBS policy or reference values are correct or current; that the pin list was written by anyone other than the holder of `mcp_servers:attest` or the config file (operator-declared trust); that Hangar's own policy is correct; that the upstream's code is benign or its outputs trustworthy; that the application container was in the hardware measurement; where the upstream runs; what Kubernetes privileges or runtime configuration its pod has; that the operator-to-core channel carrying the pin list was not tampered with (its TLS is the operator's responsibility); that a tool listed in `tools/list` has a currently reachable attested upstream (catalogues are cached; only connections are checked); that Hangar itself runs in a trusted environment; that the event log is independent of the operator. | Operates or trusts a KBS that releases per-workload leaf keys (never a CA key) only after attestation, with short validity and re-release tied to re-attestation; reads the SPKI from the KBS-provisioned resource, not from the running pod; keeps the pin list to current+next during rotation and removes a key from it as soon as the KBS revokes it; sets `tls.max_connection_age` to the longest time a single connection may go without being re-checked; never sets `hangar.io/allow-mutable-image` on an attested CR; sets `imageDigestPolicy: block`; runs `hangar.url` over TLS; never runs the same server as plaintext "temporarily"; separates the identity holding `mcp_servers:attest` from the identity operating the KBS where the threat model requires it. |

### Acceptance tests

Each row is an acceptance criterion of the clause it names. All rows except T22 run without hardware: a self-signed leaf generated in the test, a local TLS server that records what it received, and envtest for the operator.

| # | Test | Clause | Layer | Needs hardware |
| --- | --- | --- | --- | --- |
| T1 | `attested: true`, peer key in pin list: call succeeds; `ToolInvocationCompleted.upstream_peer_spki` equals the key read from the socket, not the config | §5, §6 | integration (local TLS server, self-signed) | no |
| T2 | Peer key not in pin list, chain otherwise valid (signed by a CA given in `ca_cert_path`, which is ignored): `attested_upstream_key_mismatch`; the test server asserts zero application bytes received | §2, §5 | integration | no |
| T3 | Same as T2 via a group member and via a retry on a second connection: the refused attempt records `observed_peer_spki`, the served attempt records its own key; no cross-attribution | §6 | integration | no |
| T4 | `endpoint: http://` with `attested: true`: refused at load naming both halves | §4 | unit | no |
| T5 | `attested: true` with empty `spki_sha256` or no `key_ref`, or on `mode: subprocess`/own-container mode, or with `verify_ssl: false`: refused at load | §4 | unit | no |
| T6 | Pod IP reused by a different server with a different key: refused on the next connect; MCP session renegotiation (#1852) does not bypass the check because it reuses or re-opens a transport connection that was checked | §2 | integration | no |
| T7 | Through the command bus against a real local TLS server, not a mocked start: `COLD` server, key mismatch at first contact: `_gate_cold_start` records `hangar.gate.outcome=deny`, `hangar.gate.reason=attested_upstream_key_mismatch`, never `start_failed`, and `ToolCallRefused.observed_peer_spki` is set; warm server: `ToolInvocationFailed.failure_code` set; `ToolInvocationError` to the caller in both; the same for a plaintext peer and a failed handshake with their own codes | §5, §6 | integration | no |
| T8 | Rotation: pin list `[old, new]`, server switches key: calls continue and digest pins are still honoured; list changed to `[new]` while a pooled connection is on old: that connection is closed after its in-flight request, the next call re-handshakes and is refused; an open GET stream on old is closed and re-opened; `max_connection_age` elapsed: the next call re-handshakes | §2, §5, §7 | integration (local TLS server, clock) | no |
| T9 | Server without `tls.attested` keeps today's TLS behaviour including the `verify_ssl: false` warning; no audit field, no metric series; existing TLS tests unchanged | §10 | unit | no |
| T10 | `_GATES` length and order unchanged; `_GATE_REASONS` contains the three new codes and nothing else new; no new exception type is in `_GATE_ERRORS`; none derives from `OSError` | §5 | unit | no |
| T11 | CRD: `tls.attested` + `mode: container` without `runtimeClassName`: rejected by CEL; `tls.attested` with empty `spkiSha256` or no `keyRef`: rejected; `mode: remote` without `runtimeClassName`: admitted | §4 | envtest | no |
| T12 | `runtimeClassName` on `MCPServerSpec` reaches `PodSpec.RuntimeClassName`; operator RBAC still reads no Secrets | §4 | unit (builder) + existing RBAC test | no |
| T13 | Operator POSTs a container-mode attested CR with endpoint and `tls` block and emits no discovery annotations for it; REST create/update accept `tls` and update accepts `endpoint`; the commands carry them; a pod discovered under the same name, with any annotations, is refused with `discovered_attested_upstream_without_tls` after the registration, and replaced by the registration when discovered first; after a replica restart the server is still attested; the operator does not register against a core that does not advertise the capability | §4 | envtest + core unit | no |
| T14 | `MCPDiscoverySource` with an attested `providerTemplate` is rejected by CEL, for Pod- and Namespace-type sources; an attested CR carrying `hangar.io/allow-mutable-image` is refused at admission | §4 | envtest | no |
| T15 | Exporters JSON/CEF/LEEF/syslog write `upstream_peer_spki` and `failure_code`; absent when no verified connection; CEF mapping documented | §6 | unit | no |
| T16 | Metric registered in `_register_all_metrics()` and on `/metrics` after one connect | §6 | unit | no |
| T17 | Provenance enum and serialisation unchanged; the `tls` block round-trips through `snapshot_of`/`server_from_snapshot`, and a second replica rebuilt from the snapshot serves the server as attested with the same pins; a snapshot row whose `tls.attested` cannot be restored is refused | §10 | unit | no |
| T18 | import-linter: no attestation SDK imported anywhere; SPKI hashing and peer verification live only in `http_client.py` | §3 | lint | no |
| T19 | REST: a `developer` key cannot set `tls.attested` or `peer_identity`, update the endpoint of an attested server, delete it, or create a server under its name (403); `kubernetes-operator` and `admin` can | §9 | unit | no |
| T20 | `upstream_identity()` returns `attested:<key_ref>` for an attested server, identical before any connection, after a key rotation and on a second replica; digest pins bound to it survive an endpoint change and a rotation; a different `key_ref` behind the same endpoint is a different identity; a second server with the same `key_ref` is refused; a pin-list update sharing no key with the previous list is refused unless `key_ref` changes | §7 | unit | no |
| T21 | `mcp-hangar why` lists a cold-start refusal (`ToolCallRefused`) and a warm failure (`ToolInvocationFailed`) of an attested upstream, each with expected pins and observed key; it never shows a synthesised `ToolCallRefused` for a warm transport failure | §6 | unit (SQLite) | no |
| T22 | End-to-end on kind with `kata-qemu-coco-dev`, Trustee sample attester, KBS releasing a leaf key to the guest; operator pins its SPKI: T1 passes; the docs page states this proves integration, not security | Neutral | nightly e2e (KVM) | yes |

T1–T3, T6 and T8 are also the `attested-upstream/` cases for the MCP Gateway Security Bench; T2 and T3 are the critical ones (zero bytes to a mismatched peer) and must use a test-controlled server that records what it received.

## Alternatives Considered

### 1. Verifier result as a verdict input with TTL

- **Rejected**: Hangar would consume an Attestation Result (EAT) from Trustee AS, bound to `upstream_identity()`, with `maxAge`, a new `_gate_attestation` in `_GATES`, an `AttestationResultRecorded` event in `pin_ledger`, persistence on the fleet snapshot and propagation via the event tail. The defects that decide it: (a) for operator pods `upstream_identity()` is `remote:http://<pod_ip>:<port>`, so the binding is to an IP the CNI reuses and the snapshot/replay machinery is dead weight; (b) with TTL and no channel binding, a pod-create attacker who inherits the IP inside `maxAge` receives calls audited as `attestation_status=ok`, a claim Hangar could not stand behind; (c) verification as a `PROJECTION` handler on `McpServerStarted` violates `HandlerKind` (network I/O, publishes), and as an `EFFECT` it runs once per replica because every replica emits `McpServerStarted`; (d) a `_GATES` entry cannot govern prompts/resources or group listings, which are decided elsewhere (`is_governed_allowed`, `flat_tool_projection.py:218-221`); (e) `referenceValues[kind=image-digest]` is not something an SNP/TDX verifier attests.

### 2. KBS-only: the attested guest gets its downstream credential from the KBS, Hangar is unchanged

- **Adopted as the baseline, insufficient on its own**: §1 preserves it. It gives no channel binding: Hangar still dials an IP and cannot tell an attested pod from one that inherited its address, and the audit trail cannot say which it was. The decision adds exactly one thing: the KBS also releases the upstream's TLS leaf key, and Hangar pins its SPKI.

### 3. CA-anchored identity: pin an issuer CA and match a SAN

- **Rejected**: three independent defects. A CA private key released to guests lets any admitted guest mint any name; a CA kept at an issuer makes the SAN a statement of an issuance policy Hangar cannot inspect, so `peer_identity.san` would mean whatever the issuer's rules mean; and the client's hostname verification (`sni_hostname`, `http_client.py:267-270`; CPython matches DNS/IP SANs only) rejects a URI SAN and cannot match a static leaf against a CNI-assigned pod IP. SPKI pinning (§2) needs no chain, no name and no issuance policy on Hangar's side, and shrinks the trust root to "who may write the pin list". Cost: rotation is a pin-list change (a list and `max_connection_age` make the window workable), and the operator must read the SPKI from the KBS resource it provisioned.

### 4. Sidecar or mesh mTLS termination with SPIFFE policy, Hangar untouched

- **Not chosen; compatible for enforcement, loses the audit field**: a mesh that terminates mTLS beside the upstream and admits only SVIDs gated on attestation enforces the same property without any Hangar change; Hangar then sees plaintext to a local sidecar and cannot record which key answered. A deployment that already runs such a mesh may prefer it; this record does not stand in its way and does not claim its audit guarantees for it.

### 5. Hangar itself in a TEE, policy measured, log signed by an enclave key

- **Rejected**: it changes the product from a fleet-level policy enforcement plane into an attested single-process gateway — the same widening-under-pressure that ADR-010 refused for SaaS. It needs an attestation provider abstraction, key release, freshness and rollback protection for Hangar's own log. HA (ADR-020) assumes N replicas over one log; enclave-held signing keys per replica need either a migratable sealed key or N keys and a verifier that knows them. Nothing here forbids a later record on it; it must supersede this clause explicitly.

### 6. Hangar issues the nonce and verifies Evidence

- **Rejected**: MCP has no in-band channel from an intermediary to the upstream's Attestation Agent; a nonce would travel out of band (`_meta`, a header), which is a protocol change under discussion elsewhere (AttestMCP, Enclawed mcp-attested), not a Hangar change. SNP/TDX quote verification in core duplicates Trustee and Veraison and brings platform cryptography into the domain.

### 7. RA-TLS (X.509 with the quote in an extension) to the upstream

- **Deferred**: it is the stronger form of §2: the client verifies the quote inside the handshake rather than trusting a KBS-gated key release. It needs an RA-TLS-aware client and a verifier at handshake time. The KBS-brokered form chosen here gives the same channel-binding property with the client Hangar already has, at the cost of trusting the KBS operator (§9a). If an upstream ecosystem standardises RA-TLS, a record can add it as a second `peer_identity` kind without touching anything else.

### 8. OPA-only: the fact in context, policy in Rego

- **Rejected**: OPA authorization for `hangar_call` runs before target resolution and with an empty context (`server/tools/batch/__init__.py:245`, ADR-028 §2); filling it would mean restructuring `_authorize_calls` to run after resolution, which is an ADR-028 amendment, and OPA is optional, so an installation without it would have no enforcement at all. Connect-time enforcement works in every configuration.

### 9. SPIRE with a TPM/TEE node attestor issuing SVIDs

- **Not chosen; compatible under a condition**: a SPIRE-issued SVID is a key like any other; if the operator pins its SPKI, nothing in §2 changes. Two caveats: SPIFFE/SPIRE is compatible only when SVID issuance is gated by an attestation policy that satisfies the declared trust model — a TPM node attestor proves the node booted a measured stack, not that this process runs in a TEE, and plain SPIRE with `attested: true` would claim more than the environment provides; and SVID rotation is frequent, so the pin list must be fed from the SPIRE trust bundle or the deployment must pin the SPIRE CA instead — which is Alternative 3 with its SAN problems. The record keeps SPKI pinning as the only mode and lets SPIRE deployments decide whether the rotation cost is acceptable.

### 10. Admission-time-only verification (Kata policy hash gates the KBS; Hangar unchanged)

- **Insufficient alone**: same reason as Alternative 2. It secures what runs; it does not bind what Hangar dials to what runs.

### 11. Attestation declared on MCPServerGroup

- **Rejected**: the connection is per upstream; a group is a projection over members and a declaration there would have to be fanned out — the key-mismatch class of #1036/#1040. A group may contain attested and non-attested members; each member's `tls` block decides.

### 12. A new CRD API version for the new fields

- **Rejected**: `runtimeClassName` and `tls` are additive and optional; absent means today's behaviour. Optional fields added to a served version are backward compatible for existing objects and clients, which is all an API version bump would buy.

### 13. Defer the decision until a deployment asks

- **Rejected**: deciding the contract before a deployment depends on it keeps that deployment from re-deriving it under pressure.

## References

- [ADR-004](ADR-004-sep-1766-digest-pinning.md), [ADR-010](ADR-010-retire-agent-cloud-tier.md), [ADR-013](ADR-013-egress-policy-enforcement-model.md), [ADR-018](ADR-018-event-sourcing-actually-wired.md), [ADR-020](ADR-020-high-availability.md), [ADR-021](ADR-021-config-file-endpoints-outside-the-ssrf-policy.md), [ADR-028](ADR-028-the-front-door-invoke-gate-is-the-tool-access-policy.md), [ADR-029](ADR-029-one-enrichment-boundary-and-a-bounded-decision-vocabulary.md) (§5 adds two reason codes under its rule)
- mcp-hangar/mcp-hangar: `domain/model/mcp_server.py:578-597` (`upstream_identity`), `server/tools/batch/executor.py:473-476, 2234, 3104-3117`, `domain/contracts/event_bus.py:13-68`, `domain/services/fleet_snapshot.py:70-125`, `domain/events/enforcement.py:351-357`, `infrastructure/discovery/kubernetes_source.py:250-287`, `infrastructure/launchers/http.py:35-51, 172-212`, `server/config.py:1279`, `server/tools/batch/__init__.py:245`, `auth/roles.py:176-195`, `server/api/mcp_servers.py:526-528`, `observability/conventions.py:145-170`, `approvals/api/routes.py:258`, `.github/workflows/release.yml:232`, `tests/ci/test_a_release_carries_verifiable_artifacts.py`
- mcp-hangar/mcp-hangar-operator: `api/v1alpha2/mcpserver_types.go`, `api/v1alpha2/mcpegresspolicy_types.go:108-119`, `api/v1alpha2/mcpdiscoverysource_types.go:31-32,47`, `pkg/provider/builder.go:83-107, 192-195`, `pkg/hangar/client.go:397-401, 485`, `internal/webhook/image_digest.go:9-21`, `internal/webhook/annotation_rules_test.go:16-19`, `internal/controller/mcpdiscoverysource_controller.go:714`, `config/admissionpolicy/image_digest.yaml`, `config/admissionpolicy/params.yaml`, `.github/workflows/release.yml:68, 121-122`
- mcp-hangar/docs: `security/VERDICT_LIMITS.md`, `operations/COMPLIANCE_POSTURE.md`
- RFC 9334 — RATS Architecture; RFC 9711 — Entity Attestation Token
- Confidential Containers — Trustee; Confidential Containers — architecture; Red Hat — CoCo attestation flow
- Forough, Kogias, Haddadi — When Agents Handle Secrets; Breaking the Protocol / AttestMCP; Metere — Attested Tool-Server Admission
