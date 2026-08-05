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
<https://github.com/mcp-hangar/hangar-operator>.

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

## Try It

1. Deploy an MCP server with annotations:

   ```bash
   kubectl apply -f - <<EOF
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: math-mcp-server
     namespace: mcp-servers
     labels:
       app.kubernetes.io/part-of: mcp
     annotations:
       mcp-hangar.io/enabled: "true"
       mcp-hangar.io/name: "k8s-math"
       mcp-hangar.io/port: "8080"
   spec:
     replicas: 2
     selector:
       matchLabels:
         app: math-mcp-server
     template:
       metadata:
         labels:
           app: math-mcp-server
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
   mcp-hangar status
   ```

   ```
   k8s-math    remote    cold    source=kubernetes:auto-discovery
   ```

5. Scale up and watch Hangar adapt:

   ```bash
   kubectl scale deployment math-mcp-server -n mcp-servers --replicas=3
   ```

## What Just Happened

The Kubernetes discovery source watches pods in the configured namespace matching the label selector. Pods with `mcp-hangar.io/enabled: "true"` annotations are registered as remote MCP servers. In `authoritative` mode, when a pod is deleted, the corresponding MCP server is deregistered.

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

> **Two limits to know before you follow this recipe.** The SSRF check applies to
> discovered endpoints, and a pod IP is private by definition, so registration of
> an HTTP-mode pod is currently refused
> ([#771](https://github.com/mcp-hangar/mcp-hangar/issues/771)). And
> `McpServerRegistered` is published in-process but never written to the event
> store, so the registration will not appear in the server's stream
> ([#772](https://github.com/mcp-hangar/mcp-hangar/issues/772)).

For declarative management, use the MCP-Hangar Operator CRDs instead. See the [Kubernetes guide](../guides/KUBERNETES.md).

## Key Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `discovery.sources[].type` | string | -- | Set to `kubernetes` |
| `discovery.sources[].mode` | string | -- | `additive` or `authoritative` |
| `discovery.sources[].namespaces` | list | all namespaces | Kubernetes namespaces to watch |
| `discovery.sources[].label_selector` | string | -- | Pod label selector |
| `discovery.sources[].allowed_namespaces` | list | -- | Namespaces a pod may be registered from; empty means "everything not denied" |
| `discovery.sources[].denied_namespaces` | list | `[kube-system, default]` | Namespaces never registered from. Wins over the allowlist |

### Kubernetes Annotations

| Annotation | Required | Default | Description |
|------------|----------|---------|-------------|
| `mcp-hangar.io/enabled` | Yes | -- | Must be `"true"` |
| `mcp-hangar.io/name` | No | Pod name | MCP Server name |
| `mcp-hangar.io/port` | No | `8080` | MCP Server port |
| `mcp-hangar.io/group` | No | -- | Auto-add to group |

## What's Next

You have discovery working. Now add authentication to control who can access your MCP servers.

--> [12 -- Auth & RBAC](12-auth-rbac.md)
