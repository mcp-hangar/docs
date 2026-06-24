# 15 -- Interceptor Discovery

> **Prerequisite:** [14 -- Upgrade 1.3: Digest Pinning](14-upgrade-1.3-digest-pinning.md)
> **You will need:** Docker, `curl`, `jq`
> **Time:** 10 minutes
> **Adds:** SEP-1763 interceptor discovery client checks

## The Problem

MCP Hangar exposes its validator and mutator capabilities through
`/interceptors/list`. Clients can use this endpoint to discover what Hangar can
validate or mutate before sending traffic through it.

In v1.3, the two interceptor entries have distinct names:

- `mcp-hangar-validator`
- `mcp-hangar-mutator`

If your client still assumes one shared `mcp-hangar` name, it can overwrite one
entry with the other or fail uniqueness validation.

## The Config

Create a minimal config for a local Docker smoke test:

```bash
mkdir -p /tmp/hangar-interceptors
printf 'mcp_servers: {}\n' > /tmp/hangar-interceptors/config.yaml
```

No MCP servers are required. `/interceptors/list` describes Hangar itself.

## Try It

1. Start Hangar 1.3 in HTTP mode

   ```bash
   docker run -d --name hangar-interceptors \
     -p 127.0.0.1:8000:8000 \
     -v /tmp/hangar-interceptors/config.yaml:/config.yaml:ro \
     python:3.11-slim sh -lc '
       pip install --quiet "mcp-hangar==1.3.0" &&
       mcp-hangar --config /config.yaml serve \
         --http --host 0.0.0.0 --port 8000 --unsafe-no-auth
     '
   ```

   `--unsafe-no-auth` is only for this local smoke test. Do not use it for a
   production deployment.

1. Wait for readiness

   ```bash
   until curl -fsS http://localhost:8000/health/ready 2>/dev/null; do sleep 2; done
   ```

   Expected output:

   ```json
   {"status":"healthy","ready_mcp_servers":0,"total_mcp_servers":0}
   ```

1. Fetch interceptor capabilities

   ```bash
   curl -s http://localhost:8000/interceptors/list | jq
   ```

   Expected output:

   ```json
   {
     "interceptors": [
       {
         "name": "mcp-hangar-validator",
         "version": "1.3.0",
         "type": "validator",
         "supportedEvents": ["tools/call", "tools/list"],
         "modes": ["audit", "enforce"],
         "trustBoundary": "host"
       },
       {
         "name": "mcp-hangar-mutator",
         "version": "1.3.0",
         "type": "mutator",
         "supportedEvents": ["tools/call"],
         "modes": ["enforce"],
         "trustBoundary": "host"
       }
     ]
   }
   ```

1. Verify names are unique

   ```bash
   curl -s http://localhost:8000/interceptors/list | jq -e '
     .interceptors as $items |
     ($items | length) == ($items | map(.name) | unique | length)
   '
   ```

   Expected output:

   ```json
   true
   ```

1. Build a lookup table by interceptor name

   ```bash
   curl -s http://localhost:8000/interceptors/list | jq '
     .interceptors | map({key: .name, value: .}) | from_entries | keys
   '
   ```

   Expected output:

   ```json
   [
     "mcp-hangar-mutator",
     "mcp-hangar-validator"
   ]
   ```

1. Check the capabilities your client needs

   ```bash
   curl -s http://localhost:8000/interceptors/list | jq -e '
     any(.interceptors[];
       .name == "mcp-hangar-validator" and
       .type == "validator" and
       (.supportedEvents | index("tools/list")) and
       (.modes | index("audit"))
     )
   '
   ```

   Expected output:

   ```json
   true
   ```

1. Stop the smoke-test container

   ```bash
   docker rm -f hangar-interceptors
   ```

## What Just Happened

`/interceptors/list` returns a list of Hangar interceptor instances. In v1.3 the
validator and mutator entries use different names so SEP-1763 clients can treat
them as separate capabilities.

The important client rule is: key interceptors by `name`, then validate the
fields you care about (`type`, `supportedEvents`, and `modes`). Do not collapse
all Hangar entries into a single hard-coded `mcp-hangar` record.

## Key Config Reference

No config keys are required for discovery. The endpoint is exposed by the HTTP
server when Hangar runs in HTTP mode.

| Field | Meaning |
| ----- | ------- |
| `name` | Unique interceptor instance name |
| `version` | MCP Hangar package version |
| `type` | Interceptor role, such as `validator` or `mutator` |
| `supportedEvents` | MCP event names the interceptor handles |
| `modes` | Supported operation modes |
| `trustBoundary` | Where the interceptor runs relative to the client |

## What's Next

Use this check in integration tests for clients that consume SEP-1763 metadata.
For implementation details, see
[Interceptor Framework](../architecture/INTERCEPTOR_FRAMEWORK.md).
