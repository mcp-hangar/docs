# 11 -- Discovery: Kubernetes

> **Prerequisite:** [01 -- HTTP Gateway](01-http-gateway.md)
> **You will need:** Running Hangar, Kubernetes cluster with the MCP-Hangar Operator
> **Time:** 15 minutes
> **Adds:** Auto-discover MCP servers from Kubernetes annotations

## Prerequisites

The kubernetes discovery source needs the Kubernetes Python client, which is an
extra rather than a base dependency:

```bash
pip install mcp-hangar[kubernetes]
```

The published container image already includes it. Without it, Hangar starts,
logs `discovery_source_unavailable`, and this source discovers nothing.

This recipe requires the **MCP-Hangar Operator** running in your cluster.
The operator ships from a separate repository:
<https://github.com/mcp-hangar/mcp-hangar-operator>.

Install via Helm (from the [helm-charts](https://github.com/mcp-hangar/helm-charts) repo):

```bash
helm install mcp-hangar-operator oci://ghcr.io/mcp-hangar/charts/mcp-hangar-operator \
  --namespace mcp-hangar \
  --create-namespace
```

Verify the CRDs are installed:

```bash
kubectl get crd | grep mcp-hangar.io
# Expected:
#   mcpservers.mcp-hangar.io
#   mcpservergroups.mcp-hangar.io
#   mcpdiscoverysources.mcp-hangar.io
#   mcpegresspolicies.mcp-hangar.io
```

## The Problem

You run MCP servers as Kubernetes services. Teams deploy and scale MCP servers independently. You need Hangar to discover them from annotations without manual config updates.

## The Config

```yaml
# config.yaml -- Recipe 11: Kubernetes Discovery
discovery:
  enabled: true
  refresh_interval_s: 30
  auto_register: true                    # NEW: trust K8s annotations

  sources:
    - type: kubernetes                   # NEW: Kubernetes source
      mode: authoritative                # NEW: add AND remove on pod changes
      namespaces: ["mcp-servers"]        # NEW: watch these namespaces (top-level, plural list)
      label_selector: "app.kubernetes.io/part-of=mcp"  # NEW: filter pods
```

The source assumes Hangar runs inside the cluster and reads the pod's service
account. To run Hangar outside it -- on a laptop, against your current
kubeconfig -- add `in_cluster: false` to the source.

## Try It

1. Deploy an MCP server with annotations:

   ```bash
   kubectl apply -f - <<EOF
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: math-mcp-server
     namespace: mcp-servers
   spec:
     replicas: 2
     selector:
       matchLabels:
         app: math-mcp-server
     template:
       metadata:
         # On the POD template, not on the Deployment. Discovery lists pods and
         # reads pod annotations; Kubernetes does not copy a Deployment's own
         # labels or annotations down to the pods it creates, so anything put
         # above matches nothing.
         labels:
           app: math-mcp-server
           app.kubernetes.io/part-of: mcp
         annotations:
           mcp-hangar.io/enabled: "true"
           mcp-hangar.io/name: "k8s-math"
           mcp-hangar.io/port: "8080"
       spec:
         containers:
           - name: math
             image: my-registry/math-server:latest
             ports:
               - containerPort: 8080
   EOF
   ```

2. Expose the deployment:

   ```bash
   kubectl expose deployment math-mcp-server -n mcp-servers --port=8080
   ```

3. Verify Hangar discovers it:

   ```bash
   curl http://localhost:8000/api/discovery/sources
   ```

4. Check registered MCP servers:

   ```bash
   curl http://localhost:8000/api/mcp_servers/
   ```

   `k8s-math` is listed in `remote` mode, `cold` until its first call, with the
   description `Discovered from kubernetes`. (`mcp-hangar status` shows it too
   when it can reach the gateway, at `MCP_HANGAR_URL` or `127.0.0.1` on port
   8000 or 8080.)

5. Scale up and watch Hangar adapt:

   ```bash
   kubectl scale deployment math-mcp-server -n mcp-servers --replicas=3
   ```

## What Just Happened

The Kubernetes discovery source watches pods in the configured namespace matching the label selector. Pods with `mcp-hangar.io/enabled: "true"` annotations are registered as remote MCP servers. In `authoritative` mode, when a pod is deleted, the corresponding MCP server is deregistered once its TTL (`mcp-hangar.io/ttl`, 90 s by default) has passed since the source last reported it (*since 2.34.2*; before it nothing was removed until a restart). A cycle in which the Kubernetes API cannot be reached removes nothing; a namespace whose pod listing fails while the API answers counts as empty. See [Discovery Modes](../guides/DISCOVERY.md#discovery-modes).

*Since 2.34.2* the source registers only modes Hangar connects to: `http`, `sse` or `remote`. A pod annotated with any other `mcp-hangar.io/mode`, such as `subprocess` with `mcp-hangar.io/command`, would have Hangar run that command on its own host; it is skipped and logged once as `kubernetes_discovery_local_mode_refused`, unless the source sets `allow_local_modes: true`. Set that only when whoever can create pods in the watched namespaces is trusted to choose what Hangar runs.

Two defaults are worth knowing before you take `namespaces` out of the config.
Omitting it watches **every** namespace, not one — and whatever is watched, the
source refuses to register anything from `kube-system` or `default`, which is
the `denied_namespaces` default. So a pod annotated correctly but sitting in
`default` is discovered and then declined. It does not vanish quietly: with
`quarantine_on_failure` (on by default) it lands in quarantine carrying the
reason, listed by the `hangar_quarantine` tool and counted by
`mcp_hangar_discovery_quarantine_total`.

A discovered pod is registered through the same command as a server you create
over the REST API, so it faces the same duplicate and SSRF checks, and the
`McpServerRegistered` event carries `source: discovery:kubernetes`.

> **Both of these are fixed as of 2.5.0**, and the paragraph is kept because the
> shape of the fix is worth knowing. The SSRF check still refuses a private
> address supplied by a human, but a discovered pod IP now arrives with its
> provenance attached (`runtime_addresses`) and is accepted -- the rule is about
> who supplied the endpoint, not what it looks like
> ([#771](https://github.com/mcp-hangar/mcp-hangar/issues/771)). And
> `McpServerRegistered` is written to the event store, so a discovered
> registration survives a restart
> ([#772](https://github.com/mcp-hangar/mcp-hangar/issues/772)).

For declarative management, use the MCP-Hangar Operator CRDs instead. See the [Kubernetes guide](../guides/KUBERNETES.md).

## With More Than One Hangar

*Since 2.5.0*, discovery runs on **exactly one replica** -- the one holding the
management lease -- because three discovery loops against one estate is three
sources of truth arguing, and a follower converging the fleet off a view it does
not own would deregister what a peer had just registered.

Two consequences for a replica set:

- Every replica needs the discovery configuration, not just one. The holder can
  be any of them, and a holder without the source configured discovers nothing.
- A replica that is configured for discovery and is not the holder logs
  `discovery_idle_not_the_lease_holder` and runs no cycles. That line is the one
  to look for when nothing is being discovered anywhere.

See [25 -- Running More Than One Replica](25-multiple-replicas.md).

## Key Config Reference

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `discovery.sources[].type` | string | -- | Set to `kubernetes` |
| `discovery.sources[].mode` | string | `additive` | `additive` or `authoritative` |
| `discovery.sources[].namespaces` | list | all namespaces | Kubernetes namespaces to watch |
| `discovery.sources[].label_selector` | string | -- | Pod label selector |
| `discovery.sources[].in_cluster` | bool | `true` | Use the in-cluster service account; `false` uses your kubeconfig |
| `discovery.sources[].allowed_namespaces` | list | -- | Namespaces a pod may be registered from; empty means "everything not denied" |
| `discovery.sources[].denied_namespaces` | list | `[kube-system, default]` | Namespaces never registered from. Wins over the allowlist |
| `discovery.sources[].allow_local_modes` | bool | `false` | Let a pod annotation choose a mode Hangar runs itself (`subprocess` and the like). Must be the boolean `true` |

### Kubernetes Annotations

| Annotation | Required | Default | Description |
| ------------ | ---------- | --------- | ------------- |
| `mcp-hangar.io/enabled` | Yes | -- | Must be `"true"` |
| `mcp-hangar.io/name` | No | Pod name | MCP Server name |
| `mcp-hangar.io/mode` | No | `http` | `http`, `sse` or `remote`; another mode is refused unless `allow_local_modes` |
| `mcp-hangar.io/port` | No | `8080` | MCP Server port |
| `mcp-hangar.io/path` | No | `/mcp` | Path of the MCP endpoint on the pod |
| `mcp-hangar.io/health-path` | No | `/health` | Path the registration health check asks first |
| `mcp-hangar.io/ttl` | No | `90` | Seconds an `authoritative` source keeps the server after it stops being reported |

There is no `group` annotation.

## What's Next

You have discovery working. Now add authentication to control who can access your MCP servers.

--> [12 -- Auth & RBAC](12-auth-rbac.md)
