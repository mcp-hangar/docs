# 13 -- Production Checklist

> Before you go live, walk through this list.
> **Concept:** [What Hangar costs — and where it stops](https://mcp-hangar.io/learn/costs-and-boundaries)

## Security

- [ ] TLS termination configured (reverse proxy or load balancer)
- [ ] `auth.enabled: true` and `auth.allow_anonymous: false`
- [ ] API keys created for each service principal
- [ ] RBAC roles assigned with least-privilege
- [ ] Tool access policies set for sensitive tools
- [ ] Secrets use environment variable interpolation (`${VAR}`), not plain text in config
- [ ] Docker MCP servers use `read_only: true` and `network: none` where possible

## Reliability

- [ ] Health checks enabled on all MCP servers (`health_check_interval_s`)
- [ ] Circuit breaker thresholds tuned (`max_consecutive_failures`)
- [ ] MCP Server groups configured for critical MCP servers (at least 2 members)
- [ ] `min_healthy` set to match your SLA requirements
- [ ] Idle TTL set appropriately (300s for subprocess, 600s for containers)
- [ ] Rate limiting enabled to prevent overload
- [ ] Storage decided once: `persistence.backend` set to `sqlite` (durable
      volume) or `postgresql` -- *since 2.5.0*, a backend serves every persisted
      concern or startup is refused. On 2.4.0 and earlier: `event_store.driver:
      sqlite` plus `auth.storage.driver`, chosen separately
- [ ] If `postgresql`: the driver installed -- it is an extra, not a base
      dependency, so a pip install needs `pip install "mcp-hangar[postgres]"`.
      The published image already carries it

## Observability

- [ ] Prometheus scraping `/metrics` endpoint
- [ ] Grafana dashboards shipped by the chart (`dashboards.enabled=true`), or
      imported by hand from [`mcp-hangar/files/dashboards/`](https://github.com/mcp-hangar/helm-charts/tree/main/mcp-hangar/files/dashboards)
- [ ] Alertmanager rules configured for:
  - MCP server state transitions to DEAD
  - Circuit breaker OPEN events
  - Health check failure rate above threshold
  - Tool call error rate above threshold
- [ ] Structured JSON logging enabled (`MCP_JSON_LOGS=true`)
- [ ] Log level set to `INFO` for production (`MCP_LOG_LEVEL=INFO`)

## Configuration

- [ ] Config file reviewed for correctness (no `validate` subcommand exists)
- [ ] Hot-reload tested via the `add`/`remove` API and via `SIGHUP` (graceful config reload)
- [ ] Environment-specific configs separated (dev/staging/prod)

## Deployment

- [ ] Running behind a reverse proxy (nginx, Caddy, Envoy)
- [ ] Health probe endpoints exposed for orchestrator (`/health/live`, `/health/ready`, `/health/startup`)
- [ ] Graceful shutdown configured (SIGTERM handling)
- [ ] Resource limits set (memory, CPU) for container deployments
- [ ] Persistent volume for event store SQLite database
- [ ] Docker image pinned to specific version tag, not `latest`

## Kubernetes (if applicable)

> The MCP-Hangar Operator is an external component shipped from
> [hangar-operator](https://github.com/mcp-hangar/hangar-operator).
> See [Recipe 11](11-discovery-kubernetes.md#prerequisites) for install instructions.

- [ ] MCP-Hangar Operator installed (see [Recipe 11 prerequisites](11-discovery-kubernetes.md#prerequisites))
- [ ] CRDs applied (`MCPServer`, `MCPServerGroup`, `MCPDiscoverySource`)
- [ ] RBAC (Kubernetes) configured for operator service account
- [ ] Network policies restricting MCP server-to-MCP server communication
- [ ] Resource requests and limits in Helm values
- [ ] PodDisruptionBudget for Hangar deployment -- meaningful only with more
      than one replica, which needs the row below

## More Than One Replica (if applicable)

*Since 2.5.0.* On 2.4.0 and earlier, run a **single** instance: replicas there
disagree with each other and the failure is silent.

- [ ] One PostgreSQL every replica shares (`persistence.backend: postgresql`),
      with the driver installed on every replica -- `pip install
      "mcp-hangar[postgres]"`; the published image already carries it
- [ ] A `coordination:` block, with the **same** `lease_ttl_s` on every replica
      -- the tenure in force is written by whoever holds the lease, so one
      stale ConfigMap sets the failover window for the whole set
- [ ] Every server in `remote` mode; `subprocess`/`docker` are single-instance
- [ ] Discovery configured on **every** replica, not one -- it runs on the
      lease holder, and the holder can be any of them
- [ ] Verified pod by pod, not through the Service: exactly one answers
      `manages_fleet: true` at `GET /api/system`
- [ ] Fleet-wide request cap at the ingress -- Hangar's own limit is per pod
- [ ] Rolling update rehearsed: two versions run against one database for its
      duration

See [25 -- Running More Than One Replica](25-multiple-replicas.md).

## Testing

- [ ] Failover tested: kill a primary MCP server, verify backup takes over
- [ ] Cold start tested: invoke a tool on a cold MCP server, verify latency
- [ ] Rate limit tested: flood API, verify 429 responses
- [ ] Auth tested: invalid key returns 401, insufficient role returns 403
- [ ] Config reload tested: edit config.yaml, verify changes apply
- [ ] Recovery tested: kill all MCP servers, verify they reinitialize

## Runbook

- [ ] Incident response documented
- [ ] MCP Server restart procedure documented
- [ ] Config rollback procedure documented
- [ ] Contact list for MCP server owners maintained
