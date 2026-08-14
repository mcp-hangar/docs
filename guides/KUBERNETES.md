# Kubernetes Integration

> **New to this?** [Two Hangars, one verdict](https://mcp-hangar.io/learn/more-than-one-hangar) is the concept behind this page.

Deploy and manage MCP servers as native Kubernetes resources using the MCP-Hangar Operator.

> **The MCP-Hangar Operator is shipped from a separate repository:
> [mcp-hangar-operator](https://github.com/mcp-hangar/mcp-hangar-operator).**
> Helm charts live in [helm-charts](https://github.com/mcp-hangar/helm-charts).

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
- Helm 3.x
- kubectl configured for your cluster

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
  --set hangar.url=http://mcp-hangar-core:8080

# Verify
kubectl get pods -n mcp-hangar
```

### Configuration

```yaml
# values.yaml
operator:
  logLevel: info
  metrics:
    enabled: true
    port: 8080
  leaderElection:
    enabled: true

hangar:
  url: "http://mcp-hangar-core.mcp-hangar.svc.cluster.local:8080"
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

## MCPServer

### Basic MCP Server

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: sqlite-tools
  namespace: mcp-servers
spec:
  mode: container
  image: ghcr.io/modelcontextprotocol/mcp-sqlite:latest
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
    - name: SQLITE_DB_PATH
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
  name: github-tools
  namespace: mcp-servers
spec:
  mode: container
  image: ghcr.io/modelcontextprotocol/mcp-github:latest

  env:
    - name: GITHUB_TOKEN
      valueFrom:
        secretKeyRef:
          name: github-credentials
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
  image: ghcr.io/my-org/expensive-tool:latest

  # Start with 0 replicas - will start on first request
  replicas: 0
```

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
  name: sqlite-primary
  labels:
    mcp-hangar.io/category: database
    mcp-hangar.io/tier: primary
spec:
  mode: container
  image: ghcr.io/modelcontextprotocol/mcp-sqlite:latest
---
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: sqlite-replica
  labels:
    mcp-hangar.io/category: database
    mcp-hangar.io/tier: replica
spec:
  mode: container
  image: ghcr.io/modelcontextprotocol/mcp-sqlite:latest
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
spec:
  type: ConfigMap
  refreshInterval: "1m"

  configMapRef:
    name: mcp-server-definitions
    namespace: mcp-config
```

## Security

### Pod Security

All MCP server pods run with secure defaults:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

Override if needed:

```yaml
apiVersion: mcp-hangar.io/v1alpha2
kind: MCPServer
metadata:
  name: my-mcp-server
spec:
  securityContext:
    runAsUser: 1000
    readOnlyRootFilesystem: false  # If mcp_server needs writable fs
```

### RBAC

The operator requires cluster-level permissions:

```yaml
# Automatically created by Helm chart
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-hangar-operator
rules:
  - apiGroups: [mcp-hangar.io]
    resources: [mcpservers, mcpservergroups, mcpdiscoverysources]
    verbs: [get, list, watch, create, update, patch, delete]
  - apiGroups: [""]
    resources: [pods, secrets, configmaps]
    verbs: [get, list, watch, create, update, patch, delete]
```

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
      mcp-hangar.io/mcp_server: "true"
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

## Monitoring

### Prometheus Metrics

The operator exposes metrics at `:8080/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_operator_reconcile_total` | Counter | Total reconciliations |
| `mcp_operator_reconcile_duration_seconds` | Histogram | Reconciliation duration |
| `mcp_operator_provider_state` | Gauge | MCP server state (1 = active) |
| `mcp_operator_provider_tools_count` | Gauge | Tools per MCP server |
| `mcp_operator_provider_health_check_failures_total` | Counter | Health check failures |

### ServiceMonitor

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
            summary: "MCP MCP Server {{ $labels.name }} is degraded"

        - alert: MCPServerDead
          expr: mcp_operator_provider_state{state="Dead"} == 1
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "MCP MCP Server {{ $labels.name }} is dead"
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

- Check pod logs: `kubectl logs mcp-MCP server-<name> -n <namespace>`
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
- Check MCPDiscoverySource status
- Review operator logs for discovery errors

## API Reference

### MCPServer Spec

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mode` | string | Yes | - | `container` or `remote` |
| `image` | string | For container | - | Container image |
| `endpoint` | string | For remote | - | HTTP endpoint URL |
| `replicas` | int | No | `1` | Desired replicas (0 = cold) |
| `startupTimeout` | duration | No | `30s` | Startup timeout |
| `shutdownGracePeriod` | duration | No | `30s` | Pod termination grace period |
| `resources` | object | No | - | Resource requirements |
| `env` | array | No | - | Environment variables |
| `volumes` | array | No | - | Volume mounts |
| `securityContext` | object | No | secure defaults | Security context |
| `serviceAccountName` | string | No | - | ServiceAccount |
| `nodeSelector` | map | No | - | Node selection |
| `tolerations` | array | No | - | Tolerations |
| `capabilities.network` | object | No | - | Declared egress; feeds the generated `NetworkPolicy` |
| `capabilities.tools` | object | No | - | `maxCount` / `expectedTools`; drives violation events |
| `capabilities.enforcementMode` | string | No | - | `audit` or `block` |

### MCPServer Status

| Field | Type | Description |
|-------|------|-------------|
| `state` | string | Cold, Initializing, Ready, Degraded, Dead |
| `replicas` | int | Current replicas |
| `readyReplicas` | int | Ready replicas |
| `toolsCount` | int | Available tools |
| `tools` | array | Tool names |
| `lastStartedAt` | time | Last start time |
| `lastHealthCheck` | time | Last health check |
| `consecutiveFailures` | int | Failure count |
| `conditions` | array | Status conditions |

## Examples

See [examples/kubernetes/](https://mcp-hangar.io/examples/kubernetes/) for complete examples.
