<!-- verified-against: 2.35.0 -->

# Key-Pinned Upstreams

> **New to this?** [Pin an MCP server by its key](https://mcp-hangar.io/learn/pin-an-mcp-server-by-its-key) is the concept behind this page, and [Stop a rescheduled pod from answering as your MCP server](https://mcp-hangar.io/learn/stop-a-rescheduled-pod-from-answering-as-your-mcp-server) walks through it on one machine.

A remote MCP server can be pinned by its TLS key ([ADR-030](../adr/ADR-030-an-upstream-is-pinned-by-its-key-at-the-connection.md)). Hangar then accepts a connection to it only when the peer presents one of the listed keys, and it checks this inside the TLS handshake, before the first request byte. This page is the operator's reference: where a key list is declared, what each place needs, and how to rotate, observe and upgrade. Core supports it from 2.32.0, the operator from 0.17.32.

## The key list

A peer identity is a `key_ref`, which names the key lineage and survives rotation, and a list of key pins:

```yaml
mcp_servers:
  payments:
    mode: remote
    endpoint: https://payments.payments.svc:8443/mcp
    tls:
      peer_identity:
        key_ref: payments-tls
        spki_sha256:
          - sha256:06eeb57619607484302cf6ffa9ff03c37dd97cf0a5582b3712acd5a1a84e3901
      max_connection_age: 1h
```

- **A pin** is `sha256:` followed by 64 lowercase hex characters: the SHA-256 of the certificate's DER `SubjectPublicKeyInfo`, as the certificate encodes it. Read it from the certificate the upstream serves:

  ```bash
  echo "sha256:$(openssl x509 -in server.crt -pubkey -noout \
    | openssl pkey -pubin -outform der | openssl dgst -sha256 -hex | awk '{print $NF}')"
  ```

  From 2.32.1 this matches for an EC key written with explicit curve parameters too (mcp-hangar#1982); 2.32.0 refused one. Prefer named curves anyway: PKIX forbids explicit parameters (RFC 5480), and with the `openssl` macOS ships that takes `-pkeyopt ec_param_enc:named_curve`.
- **The endpoint** must be `https`. The key replaces the certificate chain and the hostname as the identity: Hangar requires TLS 1.3 and consults no CA, so a self-signed certificate is fine.
- **`max_connection_age`** (seconds, or `90s`, `30m`, `1h`; default `1h`) bounds how long one connection pool serves. When it expires, the pool is replaced and every new connection handshakes against the current list. It is refused on a server without a peer identity.
- **`issuance`** (optional) declares how the listed keys were released. The one value is `kbs-attested`, a key a Key Broker Service released only to an attested guest (ADR-030, ADR-031). Since 2.33.0 core accepts it and records it on each call as `declared_key_issuance`; it verifies none of it. Core 2.32.1 and older refuse the key at load. See [Attested keys](#attested-keys).

## Where a key list is declared

### The configuration file

A server the file declares carries its key list as above. The file is the operator-trusted source of the servers it declares, so no API permission is involved. A replica reloading the file applies a changed list.

A release before 2.32.0 ignores `tls.peer_identity` and serves such a server as a plain one, without checking its key. Do not ship the file to a replica older than 2.32.0.

### The REST API

`POST /api/mcp_servers` with a `tls` block creates a key-pinned server, and `PUT /api/mcp_servers/{id}` changes its list or endpoint. A key-pinned server registered over the API needs:

- **Durable storage.** `persistence.backend` must be `sqlite` (one gateway) or `postgresql` (several replicas). The server's name and `key_ref` are recorded there, in the peer-key name record, and that is how replicas learn of a changed list. Without durable storage the declaration is refused.
- **The permission.** Setting or changing a peer identity, changing a key-pinned server's endpoint, deleting it, and forgetting its name (`DELETE /api/mcp_servers/{id}/peer_identity`) all need `mcp_servers:peer_identity`, on top of what the route already needs (`mcp_servers:write` and `mcp_servers:lifecycle` for a delete). Of the built-in roles, only `admin` and `kubernetes-operator` hold it; a custom role can be granted it. `mcp_servers:write` is not enough. Under OPA, allow action `peer_identity` on resource type `mcp_servers`. By default OPA is asked only when RBAC denies, so its allow is enough; with `auth.opa.require_both: true` the principal must hold the permission under RBAC too.
- **Authentication.** With authentication disabled, any client of the API can set or change a key list. A key list decides which upstream a call may reach, so run authentication wherever lists are set over the API.
- **The SSRF policy.** An endpoint set over the API is checked against it. A key-pinned server is usually reached at a private address, so list the networks it may resolve into:

  ```yaml
  ssrf:
    trusted_networks:
      - "10.96.0.0/12"    # Services, for a remote server addressed by a .svc name
      - "10.244.0.0/16"   # pods, for a mode: container server reached at its pod IP
  ```

  Otherwise every such endpoint is refused with `ssrf_blocked`. Loopback can never be trusted this way.

A name keeps its key after its server is deleted, so it cannot come back as a plain server. A create under a recorded name succeeds only with that `key_ref` and the permission. Forgetting the name is a separate act, after the delete.

### The Kubernetes operator

The `MCPServer` CRD carries the same declaration:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: payments
spec:
  mode: remote
  endpoint: https://payments.payments.svc:8443/mcp
  tls:
    peerIdentity:
      keyRef: payments-tls
      spkiSha256:
        - sha256:06eeb57619607484302cf6ffa9ff03c37dd97cf0a5582b3712acd5a1a84e3901
    maxConnectionAge: 1h
```

The apiserver refuses a malformed pin, a missing `keyRef` and an `http` endpoint. For `mode: container`, the operator runs the pod and registers it at `https://<pod IP>:8080`. The pod gets no discovery annotations, and it must serve TLS on port 8080 with a listed key.

The operator registers a key-pinned server only when all of these hold. Each failure below is condition `Degraded` on the CR, with its reason:

| Requirement | Reason when it fails |
| --- | --- |
| Core lists `peer_identity` in `capabilities` of `GET /api/system/` (core 2.32.0 or newer) | `PeerIdentityNotCarried` |
| `hangar.url` is `https://` | `PeerIdentityNotCarried` |
| No `issuance` is declared, or core lists `declared_key_issuance` in `capabilities` (core 2.33.0 or newer) | `PeerIdentityNotCarried` |
| The operator's core API key holds `kubernetes-operator` | `RegistrationForbidden` |
| Core has durable storage | `RegistrationFailed` |
| The endpoint is inside `ssrf.trusted_networks` | `EndpointNotTrusted` |

Three cases do not appear as `Degraded`:

- **A private CA.** When a private CA signed core's certificate, set `hangar.tls.ca.secretName` or `hangar.tls.ca.configMapName` in the operator chart (the operator's `--hangar-ca-file`). Without it the operator cannot read core's capabilities, the reconcile fails and is retried, and the CR gets no condition for it. Read the operator's log.
- **A key that cannot read `/api/system`.** That route needs `mcp_servers:read` held at global scope. `kubernetes-operator` holds it, so this is a key without the role, or with the role bound to one tenant. The operator cannot read core's capabilities, the reconcile fails and is retried, and the CR gets no condition for it. Read the operator's log.
- **A `mode: container` server on an operator with no core to register with** (no `--hangar-url`) is held: its pod is not created, and the CR reads `Ready=False` with reason `PeerIdentityNotCarried`.

See [KUBERNETES.md](KUBERNETES.md) for the rest of the `MCPServer` fields.

## Rotating a key

The list is a set, so rotation is two edits:

1. Add the next key beside the current one, then roll out the workload with the new key.
2. Remove the old key.

A single update cannot replace the whole list under the same `key_ref`: a list that shares no key with the stored one is refused, so a typo cannot cut every trusted key at once. A new `key_ref` starts a new lineage, and its list need share nothing with the old one. It also changes the server's identity (below).

Every replica applies a changed list. It replaces its copy of the server with a cold one built from the stored row, and the old copy's connections close. A key removed from the list is trusted until that change reaches the replica.

## Identity and digest pins

A key-pinned server's upstream identity is `peer-key:<key_ref>`, not `remote:https://host:port`. Digest pins bound to it survive an endpoint change and a rotation within the lineage. Giving an existing server a peer identity, or changing its `key_ref`, changes its identity, so record its pins again with `mcp-hangar pin --write`.

## Observing it

- **A refusal** carries `observed_peer_spki`, the key the peer presented. A refused cold start is a `ToolCallRefused`, exported as status `denied` with reason `upstream_peer_key_mismatch`. A refusal on a warm connection is a `ToolInvocationFailed`, exported as status `error` with `failure_code: upstream_peer_key_mismatch`.
- **A served call** carries `upstream_peer_spki`, the verified key of the connection that served it.
- **A declared issuance.** From 2.33.0 a call to a server that declares `issuance` carries it as `declared_key_issuance`, in JSON-lines, LEEF, syslog and OTLP; CEF has no free field for it. It records what the configuration declares, never a verification.
- **Exports.** JSON-lines, LEEF, syslog and OTLP carry each field under its own format's name. CEF carries the one key a record has as `fileHash`, with `fileType` saying which (`UpstreamTlsKeyVerified` or `UpstreamTlsKeyRefused`); the refusal's code is in `reason`.
- **`mcp-hangar why`** shows a refused key next to the keys the configuration file lists now.
- **`mcp_hangar_upstream_peer_key_connections_total{mcp_server,outcome}`** counts handshakes, `verified` or `refused`, the GET stream's included. From 2.32.1 `mcp_server` is the server's id. 2.32.0 labelled it with the endpoint's host.

## Several replicas, and upgrades

Declare a key-pinned server over the API, or from the operator, only once every replica runs 2.32.0 or newer. A release before 2.32.0 does not read the row, so it does not serve the server. Its create, though, knows nothing of the name record.

- **From 2.32.1** the database refuses that create. The first 2.32.1 replica to start installs a trigger on the configuration table, which refuses a live row under a recorded name that does not carry the recorded `key_ref` (mcp-hangar#1987).
- **On 2.32.0 alone** nothing does, and the older replica can rewrite the row as a plain server and serve it unpinned.

From 2.32.1, too, the built-in roles in force are the running release's own. A 2.31.0 replica starting on a shared auth store no longer takes `mcp_servers:peer_identity` away from `kubernetes-operator` on the 2.32.1 replicas (mcp-hangar#1988). A 2.32.0 replica still reads the stored role, so it can still lose it. The two-replica cases run nightly in the live tier, against PostgreSQL and with the published 2.31.0 beside the current release.

## Attested keys

`issuance: kbs-attested` declares that a Key Broker Service released each listed key only to a guest on appraised TEE hardware whose init-data hash was the one bound to that key. That is code identity, not instance identity: any guest launched with the same init-data on accepted hardware receives the key ([ADR-031](../adr/ADR-031-a-kbs-attested-key-is-bound-to-code-identity-through-init-data.md)). Hangar records the declaration and verifies none of it.

**What each release supports.**

- Core 2.33.0 accepts `issuance`, records it on each call as `declared_key_issuance`, and lists the `declared_key_issuance` capability. Core 2.32.1 and older refuse it at load.
- Operators before 0.17.34 accept `issuance` in the CRD and register no server that declares it.
- Operator 0.17.34 carries `spec.initData` into the pod and holds a `kbs-attested` server to its rules (see [KUBERNETES.md](KUBERNETES.md)). It registers such a server only with a core that lists the `declared_key_issuance` capability, 2.33.0 or newer.

What follows is the provisioner's part, which Hangar cannot see or check. Every item is a condition of the declaration being true.

- **The key.** Generate the key pair yourself and upload the private key as a KBS resource (`POST /kbs/v0/resource/<repo>/<type>/<tag>`). Keep no copy, and list the SPKI of the public half with `key_ref` naming the resource path. A KBS resource cannot be read back by an admin, so there is no other source of the SPKI. Never take it from the running pod.
- **The resource policy.** Release the resource only when all three hold:
  - the evidence is from a TEE, not Trustee's sample evidence;
  - the guest TCB has an affirming appraisal against your reference values;
  - the init-data hash equals the hash of the whole document you bound to the key.

  A rule over the parsed init-data claims does not qualify: Trustee drops the agent policy's rules from them.
- **The agent policy**, carried in the init-data. Generate it with Kata's `genpolicy` from the exact Deployment the pod is rendered with. Get that Deployment from the operator image of the release you run: `kubectl get mcpserver NAME -o yaml | docker run --rm -i ghcr.io/mcp-hangar/mcp-hangar-operator:<version> render`. Feed it the stored object, because the pod template carries its generation. A change to the operator's rendering ships with an upgrade note, and means generating the policy again. Keep its defaults, which refuse `ExecProcess`, `ReadStream`, `WriteStream` and `SetPolicy`, and keep `AllowRequestsFailingPolicy := false`. Refusing `ReadStream` also stops `kubectl logs`, so logs leave by the workload's own channel.

  The policy goes into the init-data, so it exists before the CR does. Render the manifest you are about to apply with `metadata.generation: 1`, which is what a fresh object is stored with. With kata 4.2.0's `genpolicy`, measured end to end in the operator's T26 run:

  - It refuses four fields the operator renders for a kbs-attested pod: `automountServiceAccountToken`, `runAsNonRoot` on the pod and on the container, and the pod's `seccompProfile`. Remove each from the rendered Deployment only where it holds the safe value (`false`, `true`, `RuntimeDefault`). The policy pins the UID and GID itself, and the container keeps its own `seccompProfile`. Do not pass `-s`, which silences every field `genpolicy` does not model.
  - With the image pulled in the guest, `genpolicy` cannot read the user from the image. Set `runAsUser` and `runAsGroup` in `spec.podSecurityContext`.
  - Its default settings expect OCI 1.1.0. A current containerd sends 1.3.0, and the guest then refuses the sandbox. Add the matching `drop-in-examples/20-oci-*` file to `genpolicy-settings.d`, and pass the settings directory with `-j`.
- **The init-data.** Name the `key_ref` in it, so each key lineage has its own hash, and put no secret in it: it is public on the CR and on the pod. The hash covers the raw bytes, so a YAML `|` versus `|-` changes it. Bind the hash the operator reports in `status.initDataDigests` (`sha256` for SNP, `sha384` for TDX), not one computed from your source file.
- **Rotation.**
  1. List the next key beside the current one.
  2. Overwrite the resource.
  3. Roll the pod.
  4. Remove the old key.

  Nobody keeps the overwritten key, so a bad next key is fixed by rotating forward.

## What a key pin does not establish

A key pin proves that the connection ended at a listed key. It does not prove how the key came to be listed:

- whoever holds `mcp_servers:peer_identity`, or writes the configuration file, can list a key they control;
- a stolen key that is on the list is trusted until it is removed.

See [What a Verdict Establishes](../security/VERDICT_LIMITS.md).
