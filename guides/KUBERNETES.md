# Kubernetes Integration

> **New to this?** [Two Hangars, one verdict](https://mcp-hangar.io/learn/more-than-one-hangar) is the concept behind this page.

Deploy and manage MCP servers as native Kubernetes resources using the MCP-Hangar Operator.

> **The MCP-Hangar Operator is shipped from a separate repository:
> [mcp-hangar-operator](https://github.com/mcp-hangar/mcp-hangar-operator).**
> Helm charts live in [helm-charts](https://github.com/mcp-hangar/helm-charts),
> and both packages are listed on Artifact Hub:
> [mcp-hangar](https://artifacthub.io/packages/helm/mcp-hangar/mcp-hangar),
> [mcp-hangar-operator](https://artifacthub.io/packages/helm/mcp-hangar-operator/mcp-hangar-operator).

## Overview

The MCP-Hangar Operator provides:

- **MCPServer** - Declarative MCP server management
- **MCPServerGroup** - Aggregates member health by label selector against a `healthPolicy`
- **MCPDiscoverySource** - Automatic MCP server discovery
- **MCPEgressPolicy** - Declarative, deny-by-default egress control (which
  upstreams a server may reach, which tool calls it may make, and what happens
  on a violation). See the [Egress Policy guide](EGRESS_POLICY.md).

> **CRD API version.** These examples use `apiVersion: mcp-hangar.io/v1alpha2`.

## Installation

### Prerequisites

- Kubernetes 1.25+
- Helm 3.x or 4.x (see [Helm versions](#helm-versions))
- kubectl configured for your cluster

### Helm versions

Helm 3 and Helm 4 are both supported and CI-tested on every helm-charts PR:
lint/render under both majors, identical rendered output across them, the full
install → test → upgrade → rollback lifecycle under each, and the cross path
(installed by Helm 3, upgraded by Helm 4). The pinned versions live in the
helm-charts CI; the
[Helm versions section of the helm-charts README](https://github.com/mcp-hangar/helm-charts#helm-versions)
is the source of truth.

What the majors do differently, as observed by those CI assertions:

- **One release = one apply model.** A fresh Helm 4 install uses server-side
  apply (SSA); a release created by Helm 3 keeps client-side apply across
  Helm 4 upgrades until you opt in with `helm upgrade --server-side=true` (the
  flag takes a value). Don't mix majors on the same release ad hoc.
- **SSA turns silent overwrites into explicit conflicts** — relevant here
  because the operator chart ships its CRDs as templates. On an SSA-installed
  release, a plain out-of-band `kubectl apply --server-side` to a helm-owned
  field is refused by the apiserver (`conflict with "helm"`). If the other
  writer forces the conflict and takes the field, the next `helm upgrade` fails
  with an explicit conflict error naming the competing manager — it does
  **not** silently take the field back; `helm upgrade --force-conflicts` is the
  documented way to reclaim it. A Helm-3-created (client-side) release has none
  of this protection: the same out-of-band write goes through silently.
- **`--wait` and `helm test` are stricter under Helm 4** (kstatus judges real
  readiness — probes and conditions, not the Helm 3 pod-status heuristic). A
  deploy that "passed" under Helm 3 and fails under 4 is the check getting
  honest, not the chart regressing. One concrete flip in the other direction:
  `helm3 test --logs` exits non-zero on a *passing* test of the mcp-hangar
  chart, because Helm 3 deletes the `hook-succeeded` test pod before fetching
  its logs (Helm 4 prints the logs first); run `helm test` without `--logs`
  under Helm 3.

### Install CRDs

The Helm chart owns the CRDs (`crds.install`, on by default) and keeps them on
uninstall (`crds.keep`). There is no separate manual step:

```bash
kubectl get crds | grep mcp-hangar.io
```

### Install Operator via Helm

```bash
# Install operator (latest published chart; pin --version from the compatibility matrix)
helm install mcp-hangar-operator oci://ghcr.io/mcp-hangar/charts/mcp-hangar-operator \
  --namespace mcp-hangar \
  --create-namespace \
  --set hangar.url=http://mcp-hangar:8080  # the core chart's Service, release "mcp-hangar"

# Verify
kubectl get pods -n mcp-hangar
```

### Configuration

```yaml
# values.yaml
operator:
  logLevel: info
  metrics:
    port: 8080
  leaderElection:
    enabled: true

hangar:
  url: "http://mcp-hangar.mcp-hangar.svc.cluster.local:8080"
  existingSecret: "mcp-hangar-credentials"
  secretKey: "api-key"

resources:
  limits:
    cpu: 500m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

**Talking to core.** With `hangar.url` set, each call the operator makes to
core (server health and tools, L7 policy push) gives up after 5 seconds, retries
included, since operator 0.17.8. Before, a core that accepted connections and
never answered held a call for about 43 seconds. A core slower than that is
reported like an unreachable one and asked again on the next requeue. The
MCPServer and MCPEgressPolicy controllers also run four reconciles at once
(`--max-concurrent-reconciles`, default 4), so one server waiting on core no
longer holds up the others, pod create and delete included.

**Memory.** Since operator 0.17.9 discovery reads ConfigMaps and Services
straight from the API server instead of caching every one in the cluster, and
cached objects are kept without their `managedFields`. Pods are still cached
cluster-wide: the operator watches both its provider pods and the core gateway
pods.

## MCPServer

### Basic MCP Server

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: db-tools
  namespace: mcp-servers
spec:
  mode: container
  # A placeholder for your own image; see OFFICIAL_SERVERS.md for servers
  # you can run today.
  image: registry.example.com/your-org/db-tools:latest
  replicas: 1

  startupTimeout: "60s"

  resources:
    requests:
      memory: "128Mi"
      cpu: "100m"
    limits:
      memory: "512Mi"
      cpu: "500m"

  env:
    - name: DB_PATH
      value: /data/database.db
```

The operator checks health on its own reconcile cadence — Hangar's health
endpoint for `remote` servers, pod phase for `container` ones. There is no
per-server interval to set.

### MCP Server with Secrets

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: api-tools
  namespace: mcp-servers
spec:
  mode: container
  image: registry.example.com/your-org/api-tools:latest

  env:
    - name: API_TOKEN
      valueFrom:
        secretKeyRef:
          name: api-credentials
          key: token
```

**Restricting which tools this server may expose is not an `MCPServer` field.**
That is `MCPEgressPolicy` — see the [Egress Policy guide](EGRESS_POLICY.md).
Core's own `tools.allow_list` in `config.yaml` is a separate mechanism for a
server Hangar runs itself.

### Remote MCP Server

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: external-api
  namespace: mcp-servers
spec:
  mode: remote
  endpoint: https://api.example.com/mcp

  startupTimeout: "30s"
```

Circuit breaking lives in core (`config.yaml`), not on the CR. The operator's
own consecutive-failure cap before it marks a server Degraded is a constant, not
a setting.

### Cold Start (Scale to Zero)

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: expensive-tool
spec:
  mode: container
  # A placeholder for your own expensive provider -- deliberately not a
  # pullable name. For a provider you can actually run today, see
  # OFFICIAL_SERVERS.md.
  image: registry.example.com/your-org/expensive-tool:latest

  # 0 replicas: the operator creates no pod and reports the server Cold
  replicas: 0
```

Nothing scales a `Cold` server up on a request: neither the operator nor core
changes `replicas`. Set `replicas: 1` to start it.

`replicas` is an on/off switch: a server runs at most one pod. Since operator
0.17.10 the CRD accepts only `0` or `1` and serves no scale subresource, so
`kubectl scale` and an HPA or KEDA ScaledObject aimed at an MCPServer are
refused. Before, values up to 10 and `kubectl scale` were accepted and still ran
one pod. A stored object with a higher value keeps working on Kubernetes 1.30+
as long as an update leaves `replicas` unchanged.

**Idle shutdown is core's, not the CR's.** Hangar stops an idle backend on
`idle_ttl_s`; a server it discovers in the cluster takes core's create default
of 300s. The `MCPServer` spec has no idle field, and the discovery-entry TTL
annotation (`mcp-hangar.io/ttl`) is a different quantity — how long core keeps
an entry it has stopped seeing.

## MCPServerGroup

A group is a **status aggregator**: it selects `MCPServer`s by label, counts
their states, and reports Ready / Degraded / Available against a `healthPolicy`.
**Traffic is not routed through it** — there is no strategy, failover or session
affinity to configure, and none of those were ever honoured.

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServerGroup
metadata:
  name: database-tools-ha
  namespace: mcp-servers
spec:
  # Select mcp_servers by label
  selector:
    matchLabels:
      mcp-hangar.io/category: database

  # When does this group report Degraded?
  healthPolicy:
    minHealthyPercentage: 50
    unhealthyThreshold: 3
```

Load balancing across members of a Hangar *group* is a core feature
(`config.yaml` / `POST /api/groups`), on a different object. The operator does
not call that API.

### Label MCP servers for Grouping

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: db-primary
  labels:
    mcp-hangar.io/category: database
    mcp-hangar.io/tier: primary
spec:
  mode: container
  image: registry.example.com/your-org/db-tools:latest
---
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: db-replica
  labels:
    mcp-hangar.io/category: database
    mcp-hangar.io/tier: replica
spec:
  mode: container
  image: registry.example.com/your-org/db-tools:latest
```

## MCPDiscoverySource

### Namespace Discovery

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPDiscoverySource
metadata:
  name: team-mcp-servers
  namespace: mcp-hangar
spec:
  type: Namespace
  mode: Authoritative  # Additive or Authoritative
  refreshInterval: "5m"

  namespaceSelector:
    matchLabels:
      mcp-hangar.io/enabled: "true"

  providerTemplate:
    spec:
      startupTimeout: "60s"
      resources:
        requests:
          memory: "64Mi"
          cpu: "50m"
```

### ConfigMap Discovery

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPDiscoverySource
metadata:
  name: config-mcp-servers
  namespace: mcp-servers
spec:
  type: ConfigMap
  refreshInterval: "1m"

  configMapRef:
    name: mcp-server-definitions   # read from the source's own namespace
```

The ConfigMap holds a map of entries under the key `providers.yaml` (or the
key `configMapRef.key` names). Each entry becomes an `MCPServer` named
`<source>-<entry>` in the source's namespace:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-server-definitions
  namespace: mcp-servers
data:
  providers.yaml: |
    math:
      mode: container
      image: registry.example.com/your-org/math-mcp:1.0.0
      command: ["python", "-m", "math_server"]
      args: ["--port", "8080"]
    search:
      mode: remote
      endpoint: http://search.mcp-servers.svc:8080
```

A `mode: container` entry carries its `image`, `command` and `args` into the
server's spec (operator 0.17.5; earlier releases dropped them, and the server
was marked `Dead`). `providerTemplate.spec` is the default and a field the
entry sets wins. A container entry with no image, and no
`providerTemplate.spec.image` to fall back on, is not created: the source
lists it in `status.discoveredProviders` with `managed: false` and the reason
in `error`, and reports `Synced=False` with reason `PartialFailure`.

Whoever can write the ConfigMap chooses the image, command and arguments that
run in the source's namespace, so treat write access to it like permission to
create pods there.

**A ConfigMap source reads only its own namespace.** Since operator 0.17.5,
`configMapRef.namespace` must be empty or the source's own namespace. With the
admission webhook on, creating a source that points elsewhere, or changing its
reference to another namespace, is rejected. With the webhook off (the chart
default), the controller reads nothing and creates nothing: the source reports
`Synced=False` and `Ready=False` with reason `CrossNamespaceRefused`, a message
naming both namespaces, and a Warning Event with the same reason. Servers such
a source created before the upgrade are left running. Copy the ConfigMap into
the source's namespace and drop `configMapRef.namespace`, or delete the source.

Since operator 0.17.6 the apiserver refuses a `type: ConfigMap` source with no
`configMapRef`, and refuses a change to an existing server's `mode` (see
[Validation](#validation)). An entry that switches an existing server from
`container` to `remote`, or back, is therefore not applied: the source records
the refused update in `status.discoveredProviders[].error` on every sync until
you delete that `MCPServer`, and the next sync recreates it in the new mode.

## Security

### Pod Security

All MCP server pods run with secure defaults:

```yaml
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 65534
containerSecurityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

The two fields mirror Kubernetes' own split: `podSecurityContext` is
`corev1.PodSecurityContext` and applies to the pod, `containerSecurityContext`
is `corev1.SecurityContext` and applies to the provider container. Settings
that exist at only one level -- `readOnlyRootFilesystem`, `capabilities`,
`allowPrivilegeEscalation` -- belong to the container one.

Override if needed:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: my-mcp-server
spec:
  podSecurityContext:
    runAsUser: 1000
  containerSecurityContext:
    readOnlyRootFilesystem: false  # If mcp_server needs writable fs
```

### ServiceAccount Token

Since operator 0.17.5, provider pods do not mount a ServiceAccount token: the
operator writes `automountServiceAccountToken: false` on every pod it builds.
Before that, each pod got the namespace's default ServiceAccount token, a
bearer credential for the API server that an egress `NetworkPolicy` does not
reliably block.

A server that talks to the Kubernetes API, or uses an in-cluster client
library, opts in. Pair it with a dedicated ServiceAccount that carries only the
RBAC the server needs:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: k8s-inspector
spec:
  mode: container
  image: registry.example.com/your-org/k8s-inspector:1.0.0
  serviceAccountName: k8s-inspector
  automountServiceAccountToken: true
```

Without the opt-in such a server fails with "unable to load in-cluster
configuration" or a `401` from the API server. Existing pods keep their mount
until their next rollout.

### Governed Namespaces

A namespace labelled `mcp-hangar.io/enforce-egress=true` is opted into the
operator's egress enforcement. Two controls apply there; the
[Egress Policy guide](EGRESS_POLICY.md) covers the per-server policies built on
top of them.

**Where DNS may go.** Every policy the operator writes allows DNS (port 53)
only to named resolvers, by default the `k8s-app=kube-dns` pods in
`kube-system`. If your cluster resolves elsewhere, pods in governed namespaces
lose DNS: it fails closed. Two settings add resolvers:

| Operator flag (chart value) | Use it for | Example |
| --- | --- | --- |
| `--dns-egress-selectors` (`operator.dnsEgressSelectors`), operator 0.17.9 and later | Resolver pods that are not kube-dns: OpenShift/OKD, or a custom resolver Deployment. Each entry is `<namespace>/<key>=<value>[,...]` with at least one label. | `openshift-dns/dns.operator.openshift.io/daemonset-dns=default` |
| `--dns-egress-cidrs` (`operator.dnsEgressCIDRs`, chart 0.12.21 and later) | A resolver reached at a node-local address, such as NodeLocal DNSCache. Not for a Service ClusterIP: CNIs match `ipBlock` after the ClusterIP is translated, so name the pods instead. | `169.254.20.10/32` |

Both apply to the per-server policy, the namespace default-deny and the Vanilla
`MCPEgressPolicy` backstop; only `--dns-egress-selectors` also reaches the
Cilium backstop.

**Namespace default-deny.** The operator writes a `NetworkPolicy` named
`mcp-default-deny-egress` that denies egress to every pod in the namespace
except DNS. Since operator 0.17.5 it is owned by the Namespace and watched: a
deleted policy is recreated and an edited one restored within seconds, and it
is garbage-collected with the namespace. A policy of that name the operator
did not write -- owned by another controller, or created by hand without the
`app.kubernetes.io/managed-by: mcp-hangar-operator` label -- is neither adopted
nor overwritten. The operator emits a Warning Event `DefaultDenyNotOwned` on
the Namespace, checks again every five minutes, and applies its own policy only
once the foreign one is gone; until then the namespace has whatever egress that
policy allows. Removing the namespace label deletes only the operator's own
policy. Since operator 0.17.6, when the operator creates or repairs this policy
in a cluster where nothing is observed to enforce NetworkPolicy, it emits a
Warning Event `DefaultDenyUnenforced` on the Namespace. The policy is still
written. A probe that cannot tell emits nothing; see
[NetworkPolicy Enforcement Status](#networkpolicy-enforcement-status).

**Pod-registration webhook.** With `webhook.enabled` and
`webhook.podRegistration.enabled` set in the chart (both off by default), a pod
labelled `mcp-hangar.io/provider=<name>` is admitted only when an `MCPServer`
of that name exists in the namespace. Since operator 0.17.5 (chart 0.12.18,
which lists `UPDATE` on the rule) the webhook also gates pod updates, and the
label is immutable once a pod is admitted:

| Write on an admitted pod | Result |
| --- | --- |
| Add `mcp-hangar.io/provider` | Denied |
| Change it to another name | Denied |
| Remove it | Allowed; the pod leaves the server's egress allow-policy |
| Any update that leaves the label as it was | Allowed, so a pod whose `MCPServer` was deleted can still be cleaned up |

Before 0.17.5 a pod admitted without the label could be labelled into a
registered server afterwards and inherit that server's egress. Create the pod
with the label instead.

### RBAC

The operator requires cluster-level permissions. An excerpt of what the Helm
chart creates (`rbac.create`, on by default; the chart's
`templates/clusterrole.yaml` has the full list):

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-hangar-operator
rules:
  - apiGroups: [mcp-hangar.io]
    resources: [mcpservers, mcpservergroups, mcpdiscoverysources, mcpegresspolicies]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [""]
    resources: [configmaps]   # ConfigMap discovery sources
    verbs: [get, list, watch]
  - apiGroups: [networking.k8s.io]
    resources: [networkpolicies]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [apps]
    resources: [daemonsets]   # enforcement probe; chart 0.12.19 and later
    verbs: [get, list]
  - apiGroups: [authentication.k8s.io]
    resources: [tokenreviews]           # secure metrics; chart 0.12.26 and later
    verbs: [create]
  - apiGroups: [authorization.k8s.io]
    resources: [subjectaccessreviews]   # secure metrics; chart 0.12.26 and later
    verbs: [create]
```

Since operator 0.17.9 and chart 0.12.24 the role grants no `secrets`,
`serviceaccounts` or `pods/status`: nothing in the operator reads them (a pod's
secret and service-account references are resolved by the kubelet), and the
`secrets` grant was cluster-wide read on every Secret. The leader-election Role
is `leases` and `events` only.

### Network Policies

Restrict MCP server communication:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-isolation
  namespace: mcp-servers
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: provider  # set on every pod the operator creates
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              mcp-hangar.io/core: "true"
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              mcp-hangar.io/core: "true"
```

### NetworkPolicy Enforcement Status

An `MCPServer` that declares `capabilities.network` gets a per-server egress
`NetworkPolicy`, and its `NetworkPolicyApplied` condition reports on it. A
NetworkPolicy restricts nothing unless the cluster's CNI enforces it, and
writing one succeeds either way. Since operator 0.17.6 the condition says
`True` only when something is observed to enforce it, using the same probe as
the `MCPEgressPolicy` `BackstopEnforceable` condition (see
[Egress Policy: Status conditions](EGRESS_POLICY.md#status-conditions)):

| Probe verdict | `NetworkPolicyApplied` |
| --- | --- |
| Enforcer observed | `True` / `PolicyApplied`; the message names the enforcer |
| No enforcer observed | `False` / `PolicyWrittenUnenforced`, plus one `NetworkPolicyUnenforced` Warning Event when the condition enters this state |
| Probe could not tell | `Unknown` / `PolicyWrittenUnverified` |

Before 0.17.6 the condition read `True` / `PolicyApplied` as soon as the policy
was written, including on CNIs that do not enforce NetworkPolicy (kindnet,
flannel, a vcluster without policy sync). The policy is still written in every
case. The other reasons are unchanged: `False` / `NoPolicyNeeded` when no
network capabilities are declared, and `False` / `EgressWithheldUnpinnedImage`
for an unpinned image in a governed namespace. Since operator 0.17.7 adding or
removing the `mcp-hangar.io/enforce-egress` label reconciles every MCPServer in
the namespace within seconds; before, an unpinned server's egress was withheld
or restored only at its next poll, up to ten minutes later.

A server reading `PolicyWrittenUnenforced` or `PolicyWrittenUnverified` is not
recorded as a `capability_drift` violation: the policy exists, and the
condition carries the enforcement gap. A server whose policy is missing still
is.

An alert or readiness gate on `NetworkPolicyApplied=True` now fires on a
cluster with no NetworkPolicy enforcement. Install an enforcing CNI, or accept
the gap knowingly. If your CNI enforces NetworkPolicy but the probe does not
recognize it, start the operator with `--networkpolicy-enforcement=enforced`
(chart value `operator.networkPolicyEnforcement`, chart 0.12.21 and later).
The probe recognizes a CNI that ships no CRD (kube-router, Azure NPM, Weave
Net) by its agent DaemonSet, which needs the `apps/daemonsets` read grant the
Helm chart carries from 0.12.19. With an older chart the probe cannot list
DaemonSets, so any cluster without a recognized policy API reads `Unknown` /
`PolicyWrittenUnverified` -- including one with no enforcer at all -- and
neither `NetworkPolicyUnenforced` nor `DefaultDenyUnenforced` is emitted.

## Monitoring

### Prometheus Metrics

The operator exposes metrics at `:8080/metrics`. Since operator 0.17.10
(chart 0.12.26) the endpoint serves HTTPS with a self-signed certificate and
admits only a bearer token the API server authenticates and authorizes for
`get` on the `/metrics` URL; anything else gets 401 or 403. Before, it served
plain HTTP to any pod that could reach it, including server names, states and
reconcile errors. `--metrics-secure=false` (chart value
`operator.metrics.secure: false`) restores plain HTTP.

| Metric | Type | Description |
| -------- | ------ | ------------- |
| `controller_runtime_reconcile_total` | Counter | Total reconciliations (controller-runtime built-in) |
| `controller_runtime_reconcile_time_seconds` | Histogram | Reconciliation duration (controller-runtime built-in) |
| `mcp_operator_provider_state` | Gauge | MCP server state (1 = active) |
| `mcp_operator_provider_tools_count` | Gauge | Tools per MCP server |
| `mcp_operator_provider_health_check_failures_total` | Counter | Health check failures |

### ServiceMonitor

The chart creates one with `serviceMonitor.enabled=true` (and, with
`prometheusRule.enabled=true`, a PrometheusRule of its own for reconcile errors
and a down operator). It scrapes HTTPS with Prometheus's own ServiceAccount
token, so bind that account to the chart's `<release>-metrics-reader`
ClusterRole:

```yaml
operator:
  metrics:
    readers:
      - name: prometheus-k8s     # your Prometheus ServiceAccount
        namespace: monitoring
networkPolicy:
  metricsFrom:                   # optional: only the monitoring namespace
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: monitoring
```

An unbound Prometheus gets 403 after the upgrade: the metrics are still
produced, just unread. By hand:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mcp-hangar-operator
  namespace: mcp-hangar
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: mcp-hangar-operator
  endpoints:
    - port: metrics
      interval: 30s
      scheme: https
      bearerTokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
      tlsConfig:
        insecureSkipVerify: true   # the certificate is self-signed
```

### Alerts

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: mcp-hangar-alerts
spec:
  groups:
    - name: mcp-hangar
      rules:
        - alert: MCPServerDegraded
          expr: mcp_operator_provider_state{state="Degraded"} == 1
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "MCP server {{ $labels.name }} is degraded"

        - alert: MCPServerDead
          expr: mcp_operator_provider_state{state="Dead"} == 1
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "MCP server {{ $labels.name }} is dead"
```

## Troubleshooting

### Check MCP Server Status

```bash
# List all mcp_servers
kubectl get mcpservers -A

# Describe specific mcp_server
kubectl describe mcpserver my-mcp-server -n mcp-servers

# Check conditions
kubectl get mcpserver my-mcp-server -o jsonpath='{.status.conditions}'
```

### Check Operator Logs

```bash
kubectl logs -n mcp-hangar deployment/mcp-hangar-operator -f
```

### Common Issues

**MCP Server stuck in Initializing:**

- Check pod logs: `kubectl logs mcp-provider-<name> -n <namespace>`
- Verify image exists and is pullable
- Check resource limits

**MCP Server in Degraded state:**

- Health checks failing
- Check network connectivity to MCP server
- Verify MCP-Hangar core is running

**Hangar pod in CrashLoopBackOff right after a 2.1.0 upgrade:**

- Check the logs for `Configured subsystem is not reachable on this server`. The
  2.1.0 startup check refuses the boot when the config gates a tool behind
  `tools.approval_list` and no approval gate service exists.
- Either remove the `approval_list` entry, or stop disabling the gate
  (`approvals.enabled: false`).
- `startup_checks: {enforce: false}` downgrades the refusal to an error log if
  you need the pod up while you fix the config. See
  [Configuration → `startup_checks`](../reference/configuration.md#startup_checks).

**Discovery not finding MCP servers:**

- Verify namespace labels match selector
- Check MCPDiscoverySource status: `CrossNamespaceRefused` means a ConfigMap
  source points at another namespace; `PartialFailure` names the entries in
  `status.discoveredProviders[].error`
- Review operator logs for discovery errors

**MCP server fails with "unable to load in-cluster configuration" or a `401`
after an operator upgrade:**

- Since operator 0.17.5 provider pods mount no ServiceAccount token. Set
  `automountServiceAccountToken: true` on the server; see
  [ServiceAccount Token](#serviceaccount-token).

**Every spec change to an MCPServer is refused after an operator upgrade:**

- Since operator 0.17.6 the CRD validates without the webhook (see
  [Validation](#validation)). The `image` and `endpoint` rules apply to the
  whole `spec`, so a stored container server with no `image`, or a remote one
  with a bad `endpoint`, refuses any spec change -- `replicas`, a discovery
  re-sync -- until the same update fixes it. Metadata and status
  updates still go through.
- The per-field rules (durations, `cidr`, `expectedTools`, the length limits)
  are re-checked on Kubernetes 1.30+ only when that field changes; before 1.30
  there is no ratcheting, so a stored violation of any rule refuses every spec
  change until the same update fixes it. A stored bad
  `cidr` or `expectedTools` entry can still block the controller's status write
  when it copies the capabilities into `status.capabilities` for the first
  time.
- Find container servers with no image:

  ```bash
  kubectl get mcpservers -A -o json | jq -r '.items[] | select(.spec.mode == "container" and ((.spec.image // "") == "")) | .metadata.namespace + "/" + .metadata.name'
  ```

**`spec.mode is immutable` or `spec.targetRef is immutable`:**

- Since operator 0.17.6 neither `MCPServer.spec.mode` nor
  `MCPEgressPolicy.spec.targetRef` can be changed. Delete the object and create
  it again with the new value.

## API Reference

### MCPServer Spec

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `mode` | string | Yes | - | `container` or `remote`. Immutable since operator 0.17.6 |
| `image` | string | For container | - | Container image, at most 1024 characters |
| `endpoint` | string | For remote | - | Absolute `http` or `https` URL with a host, at most 2048 characters |
| `replicas` | int | No | `1` | `1` runs the server, `0` stops it (Cold); nothing else since operator 0.17.10 |
| `startupTimeout` | duration | No | - | Startup timeout. Accepted but not acted on; must be a non-negative duration |
| `shutdownGracePeriod` | duration | No | `30s` | Pod termination grace period; must be a non-negative duration |
| `resources` | object | No | - | Resource requirements |
| `env` | array | No | - | Environment variables |
| `volumes` | array | No | - | Pod volumes (`corev1.Volume`) |
| `volumeMounts` | array | No | - | Where the provider container mounts them (`corev1.VolumeMount`) |
| `podSecurityContext` | object | No | secure defaults | Pod-level security context (`corev1.PodSecurityContext`) |
| `containerSecurityContext` | object | No | secure defaults | Container-level security context (`corev1.SecurityContext`) |
| `serviceAccountName` | string | No | - | ServiceAccount |
| `automountServiceAccountToken` | bool | No | `false` | Mount the ServiceAccount token into the pod (operator 0.17.5; earlier releases always mounted it) |
| `nodeSelector` | map | No | - | Node selection |
| `tolerations` | array | No | - | Tolerations |
| `capabilities.network` | object | No | - | Declared egress; feeds the generated `NetworkPolicy`. An egress `cidr` must be an IPv4 CIDR such as `10.0.0.0/8` or an IPv6 one such as `fd00::/8` |
| `capabilities.tools` | object | No | - | `maxCount` / `expectedTools`; drives violation events. `expectedTools` holds at most 256 non-empty, unique names of at most 256 characters |
| `capabilities.enforcementMode` | string | No | `alert` | `alert`, `block` or `quarantine` |

### MCPServer Status

| Field | Type | Description |
| ------- | ------ | ------------- |
| `state` | string | Cold, Initializing, Ready, Degraded, Dead |
| `replicas` | int | Pods that exist, 0 or 1 (written since operator 0.17.10) |
| `readyReplicas` | int | Ready replicas |
| `toolsCount` | int | Available tools |
| `tools` | array | Tool names |
| `lastStartedAt` | time | Last start time |
| `lastHealthCheck` | time | Last health check |
| `consecutiveFailures` | int | Failure count |
| `conditions` | array | Status conditions, including `NetworkPolicyApplied` (see [NetworkPolicy Enforcement Status](#networkpolicy-enforcement-status)) |

### Validation

Since operator 0.17.6 the CRDs carry the rules that used to live only in the
validating webhooks, which are off by default (`webhook.enabled: false`). The
apiserver now refuses, on create and update and whether or not the webhook
runs:

- An `MCPServer` with `mode: container` and no `image`, or `mode: remote` and
  no `endpoint`, or an `endpoint` that is not an absolute `http`/`https` URL
  with a host.
- A negative or unparseable `startupTimeout` or `shutdownGracePeriod`.
- An `expectedTools` list with an empty or duplicate entry, more than 256
  entries, or an entry longer than 256 characters.
- An egress `cidr` that is not an IPv4 CIDR or an IPv6 CIDR (the IPv6 form is
  checked for its shape and prefix length only), and an `image` longer than
  1024 or an `endpoint` longer than 2048 characters.
- An `MCPDiscoverySource` with `type: ConfigMap` and no `configMapRef`.
- A change to `MCPServer.spec.mode`, or to `MCPEgressPolicy.spec.targetRef`.
  Delete the object and create it again instead.

Objects stored before the upgrade that break a rule stay readable and are not
rewritten, but may refuse later updates; see
[Troubleshooting](#common-issues). The webhook, when enabled, keeps only the
checks the schema cannot express (annotation opt-ins, the cross-namespace
ConfigMap reference, filter regular expressions) and its warnings.

## Examples

See [config/samples/](https://github.com/mcp-hangar/mcp-hangar-operator/tree/main/config/samples) in the operator repository for complete examples.
