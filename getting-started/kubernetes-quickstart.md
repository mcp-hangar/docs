# Kubernetes Quick Start: from an empty kind cluster to a governed deny

Start with nothing but Docker and end with a tool call that core refuses
because of a Kubernetes policy. On the way you install core and the operator
from the published charts, run one MCP server in a pod, call one of its tools
through core with an API key, and then deny that tool with an
`MCPEgressPolicy`. About ten minutes on a laptop.

Every command below runs as written, in order, in one shell.

## What you need

- Docker, and [kind](https://kind.sigs.k8s.io/) 0.30 or later
- `kubectl`, Helm 3 or 4, `curl` and `jq`
- Port 8080 free on your machine

## 1. Create a cluster

<!-- ci:walkthrough -->
```bash
kind create cluster --name hangar
kubectl -n kube-system get configmap kubeadm-config \
  -o jsonpath='{.data.ClusterConfiguration}' | grep podSubnet
```

<!-- ci:expect podSubnet: 10.244.0.0/16 -->

The second command prints kind's pod network, `podSubnet: 10.244.0.0/16`. Core
needs that range in a moment: the operator registers each server at its pod's
address, and core refuses an endpoint on a private address it was not told to
trust.

## 2. Install core and the operator

One values file serves both charts; each chart reads only its own keys. Save it
as `values.yaml`:

<!-- ci:file values.yaml -->
<!-- config-check: skip -->
```yaml
# mcp-hangar (core)
auth:
  enabled: true
  allow_anonymous: false
  api_key:
    enabled: true
persistence:
  backend: sqlite          # the first API key needs a durable store
ssrf:
  trustedNetworks: ["10.244.0.0/16"]   # kind's pod network
config:
  trustedHosts:            # the operator calls core by its Service name
    - mcp-hangar.mcp-hangar.svc.cluster.local
    - localhost
    - 127.0.0.1

# mcp-hangar-operator
hangar:
  url: http://mcp-hangar.mcp-hangar.svc.cluster.local:8080
  existingSecret: hangar-operator-key
```

Install core first. It refuses to serve HTTP on a pod address without
authentication, so `auth` is on and every call needs a key:

<!-- ci:walkthrough -->
```bash
helm install mcp-hangar oci://ghcr.io/mcp-hangar/charts/mcp-hangar \
  --namespace mcp-hangar --create-namespace -f values.yaml --wait --timeout 5m
```

Nothing can mint the first key over HTTP, because `/api/auth/**` already wants
an administrator. `mcp-hangar auth bootstrap-admin`, run inside the core pod,
grants one and prints its key once:

<!-- ci:walkthrough -->
```bash
HANGAR_API_KEY=$(kubectl -n mcp-hangar exec deploy/mcp-hangar -- \
  mcp-hangar auth bootstrap-admin --config /etc/mcp-hangar/config.yaml \
  --principal service:walkthrough --show-key | awk '/api key/ {print $NF}')
kubectl -n mcp-hangar create secret generic hangar-operator-key \
  --from-literal=api-key="$HANGAR_API_KEY"
```

The key is stored hashed, so `$HANGAR_API_KEY` in this shell is the only copy.
The operator uses the same key here to keep the page short; give it a key of
its own anywhere else.

Then the operator, which reads `hangar.url` and the Secret from the same file:

<!-- ci:walkthrough -->
```bash
helm install mcp-hangar-operator oci://ghcr.io/mcp-hangar/charts/mcp-hangar-operator \
  --namespace mcp-hangar -f values.yaml --set image.tag=0.17.36 --wait --timeout 5m
```

`--set image.tag=0.17.36` selects operator 0.17.36, the first release that
registers container servers in core itself. It stays on the command line rather
than in `values.yaml` because both charts read `image.tag`. Once the operator
chart's default image is 0.17.36 or later, drop it.

## 3. Run an MCP server in a pod

The server is a few lines of Python with two tools, `add` and `read_env`. It
runs in core's own public image, which ships the MCP SDK, so you build nothing.
Save it as `server.yaml`:

<!-- ci:file server.yaml -->
```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: notes
  namespace: mcp-hangar
spec:
  mode: container
  image: ghcr.io/mcp-hangar/mcp-hangar:2.36.1@sha256:71c6a52a8880e910f21ed05ead8178343aee721dd1ac544ebf55349d7aac213f
  env:
    - name: DEMO_TOKEN
      value: not-a-real-secret
  command: ["python3", "-c"]
  args:
    - |
      import os
      from mcp.server.mcpserver import MCPServer

      mcp = MCPServer(name="notes")

      @mcp.tool()
      def add(a: int, b: int) -> int:
          """Add two numbers."""
          return a + b

      @mcp.tool()
      def read_env(name: str) -> str:
          """Read one of the server's environment variables."""
          return os.environ.get(name, "")

      mcp.run("streamable-http", host="0.0.0.0", port=8080)
```

The operator serves a container server on port 8080 at `/mcp` and registers it
in core under the `MCPServer`'s name:

<!-- ci:walkthrough -->
```bash
kubectl apply -f server.yaml
kubectl -n mcp-hangar wait --for=condition=Ready mcpserver/notes --timeout=5m
kubectl -n mcp-hangar get mcpserver notes
```

```text
NAME    MODE        STATE   TOOLS   READY   AGE
notes   container   Ready   2       True    40s
```

## 4. Call a tool through core

Forward core's port and define a small helper. Core answers MCP over streamable
HTTP, and its reply to a `POST` is an event stream, so the helper keeps only the
`data:` line before `jq` reads it. In the default `egress` mode a client calls a
server's tool through `hangar_call`:

<!-- ci:walkthrough -->
```bash
kubectl -n mcp-hangar port-forward svc/mcp-hangar 8080:8080 > /dev/null 2>&1 &
sleep 3
call() {
  curl -s http://127.0.0.1:8080/mcp \
    -H "X-API-Key: $HANGAR_API_KEY" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hangar_call",
         "arguments":{"calls":[{"mcp_server":"notes","tool":"'"$1"'","arguments":'"$2"'}]}}}' \
    | sed -n 's/^data: //p' \
    | jq '.result.structuredContent.results[0] | {success, result: .result.structuredContent.result, error, error_type}'
}
call add '{"a": 2, "b": 3}'
call read_env '{"name": "DEMO_TOKEN"}'
```

<!-- ci:expect "result": "not-a-real-secret" -->

Both calls go through:

```json
{
  "success": true,
  "result": 5,
  "error": null,
  "error_type": null
}
{
  "success": true,
  "result": "not-a-real-secret",
  "error": null,
  "error_type": null
}
```

`read_env` hands the server's environment, `DEMO_TOKEN` included, to whoever
can call it. That is the tool to take away.

Before you do, note what the server's pod can reach. This helper opens a TCP
connection from the server's pod to core's Service:

<!-- ci:walkthrough -->
```bash
probe() {
  kubectl -n mcp-hangar exec deploy/mcp-provider-notes -- python3 -c \
    "import socket; socket.create_connection(('mcp-hangar', 8080), timeout=5)" \
    > /dev/null 2>&1 && echo reachable || echo blocked
}
probe
```

<!-- ci:expect reachable -->

It prints `reachable`.

## 5. Deny the tool

Save the policy as `policy.yaml`. `mode: Enforce` blocks instead of only
recording; `deny` wins over `allow`, so every tool but `read_env` stays
callable. The single upstream is `192.0.2.0/24`, a range reserved for
documentation, so the server may open connections to nothing real:

<!-- ci:file policy.yaml -->
```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPEgressPolicy
metadata:
  name: notes-no-env
  namespace: mcp-hangar
spec:
  mode: Enforce
  targetRef:
    kind: MCPServer
    name: notes
  defaultAction: Deny
  upstreams:
    - name: documentation-range
      match:
        host: 192.0.2.0/24
      tools:
        allow: ["*"]
        deny: ["read_env"]
```

The operator compiles the tool rules and pushes them to core. `L7Delivered`
turns `True` once core holds them:

<!-- ci:walkthrough -->
```bash
kubectl apply -f policy.yaml
kubectl -n mcp-hangar wait --for=condition=L7Delivered mcpegresspolicy/notes-no-env --timeout=2m
```

## 6. Call it again

The same two calls:

<!-- ci:walkthrough -->
```bash
call add '{"a": 2, "b": 3}'
call read_env '{"name": "DEMO_TOKEN"}'
```

<!-- ci:expect "error_type": "EgressPolicyDeniedError" -->

`add` still answers `5`. `read_env` is refused by core before anything reaches
the server:

```json
{
  "success": false,
  "result": null,
  "error": "Refused by MCP Hangar (l7): deny. See why: mcp-hangar why 846f289b-ebd7-4c74-b46e-55e70414d441\nTool call denied by egress policy",
  "error_type": "EgressPolicyDeniedError"
}
```

The first line of `error` names the layer that refused (`l7`, the egress
policy) and the correlation id to look the decision up by. `error_type` is the
stable part to match on.

## 7. See the backstop

A tool rule in core governs the calls core proxies. It does not stop the
server's own process from opening connections, so the operator also writes a
network backstop: a `NetworkPolicy` that lets the server's pod reach DNS and
the policy's upstreams, and nothing else.

<!-- ci:walkthrough -->
```bash
kubectl -n mcp-hangar get mcpegresspolicies
kubectl -n mcp-hangar get networkpolicy mcp-egresspolicy-notes-no-env -o yaml
probe
```

<!-- ci:expect blocked -->

```text
NAME           MODE      BACKSTOP     L7     TARGET   DEFAULT   AGE
notes-no-env   Enforce   Unenforced   True   notes    Deny      30s
```

The `NetworkPolicy` selects `mcp-hangar.io/provider: notes` and allows egress
to `kube-dns` on port 53 and to `192.0.2.0/24`. The probe that printed
`reachable` before now prints `blocked`: kind's network plugin enforces the
backstop.

`BACKSTOP` still reads `Unenforced`, and the policy reports `Degraded=True`
with reason `EnforcementNotObserved`. The operator decides whether anything
enforces a `NetworkPolicy` by looking for a CNI it recognises, and it does not
recognise kind's. It reports what it could establish rather than assume. On a
cluster whose CNI it does not recognise but you know enforces policy, set
`operator.networkPolicyEnforcement: enforced` in the operator chart's values.
On Calico or Cilium it reads `Enforcing` by itself.

<!-- ci:walkthrough -->
```bash
kubectl -n mcp-hangar get mcpegresspolicy notes-no-env \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status} ({.reason}){"\n"}{end}'
```

```text
Compiled=True (Compiled)
BackstopApplied=True (BackstopApplied)
BackstopEnforceable=False (NoEnforcerObserved)
Degraded=True (EnforcementNotObserved)
L7Delivered=True (Delivered)
```

<!-- ci:expect BackstopApplied=True -->

## 8. Clean up

<!-- ci:walkthrough -->
```bash
kind delete cluster --name hangar
```

## Where to go next

- [Egress Policy](../guides/EGRESS_POLICY.md): the full policy language,
  backstop flavors and every status condition
- [Kubernetes Integration](../guides/KUBERNETES.md): the operator's resources
  and governed namespaces
- [Authentication & Authorization](../guides/AUTHENTICATION.md): keys, roles
  and OIDC instead of one admin key
- [Quick Start](quickstart.md): the same idea on one laptop without a cluster
