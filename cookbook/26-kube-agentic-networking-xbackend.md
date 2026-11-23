# 26 -- Hangar as the XBackend behind kube-agentic-networking

<!-- verified-against: 2.40.0 -->

> **Prerequisite:** [16 -- Front-Door Multi-Tenant](16-front-door-multi-tenant.md), [18 -- Per-Tenant Digest Pins](18-tenant-digest-pins.md)
> **You will need:** MCP Hangar 2.40.0; [kube-agentic-networking](https://github.com/kubernetes-sigs/kube-agentic-networking) v0.2.0 with its reference controller built from the `v0.2.0` tag (commit `cff53a3`), because the tag's `k8s/deploy/deployment.yaml` pulls the controller image tagged `main`; Kubernetes 1.35 with Pod certificates and cluster trust bundles enabled, set up as the project's `dev/ci/setup-cluster.sh` does; an OIDC issuer that puts a `tenant_id` claim in its tokens
> **Adds:** Hangar as the MCP backend a kube-agentic-networking `Gateway` routes to, with an `XAccessPolicy` in front and a NetworkPolicy behind

## The Problem

kube-agentic-networking gives each agent a SPIFFE identity and lets an
`XAccessPolicy` decide, at an Envoy gateway, which agent may call which MCP
method and tool. It does not know what a tool *is*. It cannot see that an
upstream changed a tool's description, give two tenants different tool lists,
hold a call for a human, or answer with a refusal of its own.

Plugging Hangar in as the gateway's external authorizer does not fix that: the
gateway asks a yes or no question, so Hangar never serves the listing, the check
times out long before a human could approve, and the gateway replaces Hangar's
refusal body
([mcp-hangar#1807](https://github.com/mcp-hangar/mcp-hangar/issues/1807)).
Putting Hangar *behind* the gateway, as the `XBackend` it routes to, does work,
with no change to Hangar. This recipe is that deployment, as tested on a test
Kubernetes cluster
([mcp-hangar#2310](https://github.com/mcp-hangar/mcp-hangar/issues/2310)).

## Who decides what

| | `XAccessPolicy` at the gateway | Hangar behind it |
| --- | --- | --- |
| Identity it decides on | the agent's SPIFFE ID, from its mTLS certificate | the agent's JWT, sent as `Authorization: Bearer` and passed through by the gateway |
| `tools/list` | passes it through | serves it: per tenant, withholding a tool whose pin no longer matches |
| `tools/call` | allows or refuses by method and tool name | tool access lists, per-tenant policy, digest pins, approvals |
| Refusal the client sees | a fixed body, `{"error":{"code":403,"message":"Access to this tool is forbidden."}}` | Hangar's own JSON-RPC error, unchanged by the gateway |

Keep the gateway policy coarse: which agents may reach Hangar at all. Keep
tool-level policy in Hangar, which also serves the listing. Two tool lists
disagree in ways a client cannot see: Hangar lists a tool the gateway refuses,
and a gateway tool list refuses Hangar's own `hangar_whoami` unless it names it.

Hangar must run `tool_access.mode: front_door` (reasoned from how `egress` mode works, not tested). In `egress` mode the client
calls `hangar_call` with the real tool in its arguments, so the gateway's tool
rules would see one name for every call.

## The Config

Everything below lives in one namespace, `agent-gateway`: the `Gateway`, the
Envoy pods the controller creates for it, the `XBackend`, the route and Hangar.
The controller resolves an `XBackend`'s `serviceName` in the `XBackend`'s own
namespace.

### Hangar

```yaml
# config.yaml -- Recipe 26: Hangar as the XBackend

tool_access:
  mode: front_door                 # the gateway's tool names are the real ones

tool_projection:
  pin_recheck_interval_s: 60       # re-list pinned servers; drift is withheld from the next pass

approvals:
  channel: event_stream

auth:
  enabled: true
  allow_anonymous: false
  storage: {driver: sqlite, path: /data/auth.db}
  oidc:
    enabled: true
    issuer: https://idp.example.internal
    audience: mcp-hangar
    tenant_claim: tenant_id        # the front door refuses a caller without one
  role_assignments:
    - {principal: "agent-a", role: service-account, scope: global}
    - {principal: "approver-a", role: provider-admin, scope: global}   # its token must carry the tenant it approves for

mcp_servers:
  records:
    mode: remote
    endpoint: http://records.records.svc.cluster.local:8000/mcp
    tools:
      deny_list: [delete_record]
      approval_list: [archive_record]
    tool_access:
      member:
        "tenant-b":
          deny_list: [lookup_record]
    tool_projection:
      flat: [lookup_record, archive_record]
      digest_enforcement: block
```

Run `mcp-hangar pin --write` against the real upstream to add `pins:` to the
`records` entry; without pins there is nothing to withhold on drift. Then load
the file with
`kubectl -n agent-gateway create configmap hangar-config --from-file=config.yaml`.

The Deployment passes the gateway's address in `MCP_TRUSTED_HOSTS`. The gateway
forwards the `Host` the agent used, `<gateway address>:10001`, and Hangar
answers `421 Invalid Host header` to a host it does not trust. Give the
`Gateway` a stable DNS name rather than trusting a load-balancer IP that can
change. `hangar` and `hangar:8080` are for callers that reach the Service
directly, such as approvers.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: hangar, namespace: agent-gateway}
spec:
  replicas: 1
  selector: {matchLabels: {app: hangar}}
  template:
    metadata: {labels: {app: hangar}}
    spec:
      containers:
        - name: hangar
          image: ghcr.io/mcp-hangar/mcp-hangar:2.40.0
          args: ["--config", "/config/config.yaml", "serve", "--http", "--host", "0.0.0.0", "--port", "8080"]
          ports: [{containerPort: 8080}]
          env:
            - {name: MCP_TRUSTED_HOSTS, value: "agents-gw.example.internal:10001,hangar,hangar:8080"}
          volumeMounts:
            - {name: config, mountPath: /config}
            - {name: data, mountPath: /data}
      volumes:
        - {name: config, configMap: {name: hangar-config}}
        - {name: data, persistentVolumeClaim: {claimName: hangar-data}}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: hangar-data, namespace: agent-gateway}
spec:
  accessModes: [ReadWriteOnce]
  resources: {requests: {storage: 100Mi}}
---
apiVersion: v1
kind: Service
metadata: {name: hangar, namespace: agent-gateway}
spec:
  selector: {app: hangar}
  ports: [{port: 8080, targetPort: 8080}]
```

### Gateway, XBackend and route

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata: {name: agents-gw, namespace: agent-gateway}
spec:
  gatewayClassName: kube-agentic-networking
  listeners:
    - {name: https, protocol: HTTPS, port: 10001, allowedRoutes: {namespaces: {from: Same}}}
---
apiVersion: agentic.networking.x-k8s.io/v0alpha0
kind: XBackend
metadata: {name: hangar, namespace: agent-gateway}
spec:
  mcp: {serviceName: hangar, port: 8080, path: /mcp}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: {name: hangar, namespace: agent-gateway}
spec:
  parentRefs: [{name: agents-gw}]
  rules:
    - matches: [{path: {type: PathPrefix, value: /hangar}}]
      filters:
        - {type: URLRewrite, urlRewrite: {path: {type: ReplacePrefixMatch, replacePrefixMatch: /mcp}}}
      backendRefs: [{group: agentic.networking.x-k8s.io, kind: XBackend, name: hangar}]
```

The tested setup ran the controller's default proxy image,
`envoyproxy/envoy:v1.36-latest` (its `--proxy-image` flag). Pin a v1.36 patch
tag in production.

### The access policy

The tested policy names the tools. List every tool Hangar projects that the
agent may use, `hangar_whoami` and any other `hangar_*` tool included; a
policy that admits every `tools/call` without a list was not tested.

```yaml
apiVersion: agentic.networking.x-k8s.io/v1alpha1
kind: XAccessPolicy
metadata: {name: hangar-coarse, namespace: agent-gateway}
spec:
  targetRefs: [{group: agentic.networking.x-k8s.io, kind: XBackend, name: hangar}]
  action: Allow
  rules:
    - name: agent-a
      source: {type: ServiceAccount, serviceAccount: {name: agent-a, namespace: agent-gateway}}
      authorization:
        type: Inline
        mcp:
          mcpBaseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS
          methods:
            - {name: tools/call, params: ["lookup_record", "archive_record", "hangar_whoami"]}
```

The agent pod runs as the ServiceAccount the policy names
(`kubectl -n agent-gateway create serviceaccount agent-a`), gets its SPIFFE
certificate from the controller's signer through a projected volume, and
presents it to the gateway with its JWT for Hangar. The relevant part of its
spec:

```yaml
spec:
  serviceAccountName: agent-a
  containers:
    - name: agent
      image: <your agent image>
      volumeMounts:
        - {name: agent-identity-mtls, mountPath: /run/agent-identity-mtls, readOnly: true}
  volumes:
    - name: agent-identity-mtls
      projected:
        sources:
          - clusterTrustBundle:
              signerName: kube-agentic-networking.sigs.k8s.io/identity
              labelSelector:
                matchLabels:
                  "kube-agentic-networking.sigs.k8s.io/canarying": "live"
                  "kube-agentic-networking.sigs.k8s.io/workload-trust-domain": "cluster.local"
                  "kube-agentic-networking.sigs.k8s.io/peer-trust-domain": "cluster.local"
              path: cluster.local.trust-bundle.pem
          - podCertificate:
              signerName: kube-agentic-networking.sigs.k8s.io/identity
              keyType: ECDSAP256
              credentialBundlePath: credential-bundle.pem
```

### The NetworkPolicy

Without it, any pod that can reach the `hangar` Service skips the gateway's
policy: in the test, a direct call ran a tool the gateway refuses. Hangar's own
checks still applied there, because it authenticates the JWT itself. The
controller labels its Envoy pods with the `Gateway`'s name, so admit only those:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: hangar-only-from-gateway, namespace: agent-gateway}
spec:
  podSelector: {matchLabels: {app: hangar}}
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector: {matchLabels: {gateway.networking.k8s.io/gateway-name: agents-gw}}
      ports: [{port: 8080}]
```

With it applied, the direct call timed out and the gateway path kept working.

Approvers resolve over Hangar's REST API (`POST /api/approvals/{id}/resolve`),
which this policy also closes. In the test they reached it before the policy
was applied. To keep that path, add a second `from` entry for the namespace
your approvers or approval adapter run in. That rule was not tested, and it
opens `/mcp` on the same port to that namespace too; Hangar's JWT check still
applies there.

### With the Helm chart

The `mcp-hangar` chart already has what this needs:

- `config.trustedHosts` renders `MCP_TRUSTED_HOSTS`. List the gateway's
  `host:port`.
- `networkPolicy.enabled: true` (the default) admits the release namespace on
  the service port. With the `Gateway` and Hangar alone in that namespace and
  agents elsewhere, only the Envoy pods qualify. Any other pod in the namespace
  is admitted too.
- `networkPolicy.allowMonitoring: true` opens the same port to the monitoring
  namespace. Set it to `false`, or accept that namespace as a caller that
  Hangar still authenticates.
- `networkPolicy.additionalIngress` is where the approvers' namespace goes.
- Install the release in the `Gateway`'s namespace and set the `XBackend`'s
  `serviceName` to the chart's Service. An upstream outside that namespace on
  a port other than 443 needs a `networkPolicy.additionalEgress` rule.

This was checked with `helm template`, not on a cluster.

## Try It

Send MCP requests to `https://agents-gw.example.internal:10001/hangar` with the
pod's certificate and a token from your issuer:

```bash
curl -s --cert /run/agent-identity-mtls/credential-bundle.pem \
  --key /run/agent-identity-mtls/credential-bundle.pem \
  --cacert /run/agent-identity-mtls/cluster.local.trust-bundle.pem \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H 'mcp-protocol-version: 2025-11-25' \
  --data-raw '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  https://agents-gw.example.internal:10001/hangar
```

What the test saw from one pod, with an `echo` tool projected as well:

- A `tenant-a` token listed `lookup_record`, `archive_record`, `echo` and
  `hangar_whoami`. A `tenant-b` token did not list `lookup_record`. A token
  with no tenant listed only `hangar_whoami`, because the front door fails
  closed.
- The upstream changed `lookup_record`'s description without announcing it.
  After the next re-check the gateway path no longer listed it and refused a
  call of it, while a route straight to the upstream served the poisoned text.
- A call of `archive_record` was held, approved over the REST API after 6 s,
  and ran.

### Which refusal the client sees

| Refused by | Case | Client sees |
| --- | --- | --- |
| Gateway | tool not in the `XAccessPolicy` list | HTTP 200, `{"error":{"code":403,"message":"Access to this tool is forbidden."},"id":3,"jsonrpc":"2.0"}` |
| Hangar | deny-listed, tenant-denied, drifted or never projected | HTTP 200 SSE, `{"jsonrpc":"2.0","id":5,"error":{"code":-32601,"message":"Tool 'lookup_record' not found"}}` |
| Hangar | no credential | HTTP 401 with `www-authenticate: Bearer ..., ApiKey` and Hangar's JSON body |
| Gateway, after Hangar held the call | approval later than 15 s | HTTP 200 SSE that closes with no message |

## Limits

- **Two credentials, bound only by the NetworkPolicy.** The gateway decides on
  the SPIFFE ID and Hangar on the JWT. Nothing ties the token to the workload
  presenting it: one pod presented a `tenant-a` and a `tenant-b` token and was
  each tenant in turn. v0.2.0 cannot check the JWT at the gateway, since its
  OIDC sources are not implemented. Hangar has no way to accept the gateway's
  SPIFFE ID as a principal; that identity bridge is deferred until the gateway
  forwards a verified identity.
- **Do not trust identity headers from the gateway.** It strips a forged
  `x-forwarded-client-cert` and forwards no SPIFFE ID; every other client
  header, `x-user-id` included, reaches Hangar as the client sent it. The hop
  from Envoy to an in-cluster `XBackend` is plain HTTP.
- **The gateway cuts every request at 15 s.** Envoy sends
  `x-envoy-expected-rq-timeout-ms: 15000`, and `HTTPRoute`
  `timeouts.request` was accepted but had no effect. An approval must resolve
  within 15 s, whatever `approval_timeout_seconds` says. An approval at 22 s
  was refused with `Approval refused: the held call was cancelled and did not
  run`, and the tool did not run. The `GET` event stream is cut at the same
  point, so a client must reconnect.
- **Approvers need the caller's tenant.** A held call carries its tenant, and
  only an approver whose token carries the same tenant sees and resolves it. A
  global `provider-admin` with no tenant lists none
  ([mcp-hangar#688](https://github.com/mcp-hangar/mcp-hangar/issues/688)).
- **API keys cannot use this front door.** They carry no tenant, so every
  key-authenticated caller saw zero tools.
- **Latency.** On a laptop cluster, not a benchmark, the gateway hop cost about
  0.6 ms and Hangar's front door about 26 to 33 ms per `tools/call` (p50, tracing
  off; about 5 ms of it logging). It is not profiled yet
  ([mcp-hangar#2311](https://github.com/mcp-hangar/mcp-hangar/issues/2311)).

## Key Config Reference

| Setting | Where | Why here |
| --- | --- | --- |
| `tool_access.mode: front_door` | Hangar config | the gateway's tool rules see real tool names |
| `auth.oidc.tenant_claim` | Hangar config | the front door needs a tenant per caller |
| `tool_projection.pin_recheck_interval_s` | Hangar config | how soon an unannounced change is withheld |
| `MCP_TRUSTED_HOSTS` | Hangar environment | the `Host` arrives as the gateway's address |
| `XAccessPolicy` | gateway | who may reach Hangar at all |
| NetworkPolicy | cluster | only the gateway reaches Hangar |

## What's Next

[23 -- Harden a Public Authenticated Gateway](23-harden-public-gateway.md) for
the rest of the production checklist.
