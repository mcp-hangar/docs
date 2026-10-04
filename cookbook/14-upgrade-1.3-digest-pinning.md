# 14 -- Upgrade: Digest Pinning (v1.2.1 JCS change)

> **Prerequisite:** [13 -- Production Checklist](13-production-checklist.md)
> **You will need:** Docker, MCP Hangar 1.2.0 (or earlier) with pinned tool digests
> **Time:** 20 minutes plus one audit window
> **Adds:** Safe migration to RFC 8785 JCS digests (introduced in v1.2.1)
> **Concept:** [Digest pinning: tool schemas can't drift under you](https://mcp-hangar.io/learn/digest-pinning)

## The Problem

MCP Hangar v1.2.1 changed how tool digests are computed. Releases up to v1.2.0
used Python `json.dumps` canonicalization. Starting in v1.2.1, Hangar uses
RFC 8785 JSON Canonicalization Scheme (JCS), normalizes empty optional values,
and rejects malformed tool entries before hashing. That digest behavior carries
forward unchanged through every release since, so this migration
applies whether you land on v1.2.1 or any later version.

If you upgrade across the v1.2.1 boundary with strict digest enforcement, valid
tools can look like drift because their old pins were computed with the previous
algorithm. You need to refresh pins without creating a production outage.

Check first whether you have such pins at all. Up to v1.3.0 the digest code
was a library -- `compute_tool_digest`, `DigestPolicy` and a standalone
`DigestValidator` -- and nothing in `config.yaml` pinned a digest or enforced
one. Configured pins arrived in v1.4.0, per tenant under
`tool_projection.tenant_overrides.<tenant>.pins` (all-tenant
`tool_projection.pins` followed in 2.6.0), and were computed with JCS from the
start. So the json.dumps-era digests this recipe migrates exist only where your
own code called `compute_tool_digest` on v1.2.0 or earlier and stored the
result.

## The Config

Keep your existing `config.yaml`. This recipe changes the rollout posture, not
the MCP server layout.

Before upgrading, identify every place where digest policy is defined:

```bash
for path in ~/.config/mcp-hangar ./config.yaml ./configs; do
  [ -e "$path" ] && grep -R "allow_degraded\|allow_unverified\|digest\|pinned" "$path"
done
```

`allow_degraded` and `allow_unverified` are values of the Python
`DigestUnknownPolicy` type, not settings: no `config.yaml` key has ever read
either. If your own code still passes `allow_degraded`, change it to
`allow_unverified` (the rename also shipped in v1.2.1):

```diff
- allow_degraded
+ allow_unverified
```

Since v1.4.0, digest enforcement is set per server with
`tool_projection.digest_enforcement` (a group can carry one too in 2.24.0),
and it defaults to `block`. During the
migration window, run it in `audit` or `warn` mode. Do not use `block` until
every pin has been recomputed under the JCS algorithm.

```yaml
mcp_servers:
  math:
    mode: remote
    endpoint: http://localhost:8080/mcp
    tool_projection:
      digest_enforcement: audit      # audit | warn | block (default)
      pins:                          # tool name -> 64 lowercase hex characters, no prefix
        add: a30ea916b7cc20436fde225e668af33d9a972ee082717dc6332220d015bf5a5e
```

For the Docker smoke test below, create a minimal config:

```bash
mkdir -p /tmp/hangar-1.3-cookbook
printf 'mcp_servers: {}\n' > /tmp/hangar-1.3-cookbook/config.yaml
```

## Try It

1. Record the currently pinned digests

   ```bash
   : > /tmp/hangar-digests-before.txt
   for path in ~/.config/mcp-hangar ./config.yaml ./configs; do
     [ -e "$path" ] && grep -R -A50 "pins:" "$path" >> /tmp/hangar-digests-before.txt
   done
   ```

   Keep this file until the migration is complete. It is your rollback map. A
   configured pin is a bare 64-character hex value under `pins:`; add whatever
   store your own code kept its digests in.

1. Verify the package in Docker

   This recipe installs v1.3.0 or newer, which
   includes the v1.2.1 JCS digest behavior. Any version `>=1.2.1` works.

   ```bash
   docker run --rm python:3.11-slim sh -lc '
     pip install --quiet "mcp-hangar>=1.3.0" &&
     mcp-hangar --version
   '
   ```

   Expected output:

   ```text
   mcp-hangar 2.24.0
   ```

   The version is whichever release pip resolves; the output above is from the
   run this page was checked with.

1. Start Hangar in HTTP mode

   ```bash
   docker run -d --name hangar-1.3-cookbook \
     -p 127.0.0.1:8000:8000 \
     -v /tmp/hangar-1.3-cookbook/config.yaml:/config.yaml:ro \
     python:3.11-slim sh -lc '
       pip install --quiet "mcp-hangar>=1.3.0" &&
       mcp-hangar --config /config.yaml serve \
         --http --host 0.0.0.0 --port 8000 --unsafe-no-auth \
         --log-file /tmp/hangar-1.3-digest.log
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

1. Verify interceptor discovery

   ```bash
   curl -s http://localhost:8000/interceptors/list | jq '.interceptors[].name'
   ```

   Expected output:

   ```text
   "io.mcp-hangar.validator"
   "io.mcp-hangar.mutator"
   ```

   *Since 2.0.0* the default response uses these reverse-DNS names; v1.2.1 to
   v1.6.x answered `mcp-hangar-validator` and `mcp-hangar-mutator`.

1. Exercise every pinned MCP server

   Call at least one tool from every pinned server. For grouped MCP servers,
   hit each member, not just the group name.

   ```bash
   curl -sL http://localhost:8000/api/mcp_servers/ | jq
   ```

   Expected output for the minimal smoke-test config:

   ```json
   {
     "mcp_servers": []
   }
   ```

1. Smoke-test digest normalization

   ```bash
   docker exec -i hangar-1.3-cookbook python - <<'PY'
   from mcp_hangar.domain.services.digest_computation import compute_tool_digest

   base = {
       "name": "add",
       "description": "Add numbers",
       "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}}},
   }
   with_empty = dict(base, annotations={}, title="")

   print(compute_tool_digest(base).sha256)
   print(compute_tool_digest(with_empty).sha256)
   PY
   ```

   Expected output: the same digest printed twice.

   ```text
   61ccc5d86e8ad8087d55647f94b3dd1826e8af4b01ed5d672b55800e9b5bfc53
   61ccc5d86e8ad8087d55647f94b3dd1826e8af4b01ed5d672b55800e9b5bfc53
   ```

1. Smoke-test malformed tool names

   ```bash
   docker exec -i hangar-1.3-cookbook python - <<'PY'
   from mcp_hangar.domain.services.digest_computation import compute_tool_digest

   for tool in [{"description": "missing"}, {"name": ""}, {"name": 123}]:
       try:
           compute_tool_digest(tool)
       except Exception as exc:
           print(type(exc).__name__, str(exc))
   PY
   ```

   Expected output:

   ```text
   ValueError tool missing required string field 'name'
   ValueError tool missing required string field 'name'
   ValueError tool missing required string field 'name'
   ```

1. Collect digest drift events

   ```bash
   docker exec hangar-1.3-cookbook sh -lc '
     grep -E "DigestMismatchEvent|digest.*mismatch|unknown.*digest" \
       /tmp/hangar-1.3-digest.log || true
   '
   ```

   Treat each event as a candidate new pin, not as an automatic approval. Review
   the tool name, MCP server ID, and schema before accepting the new digest.

1. Replace old pins with JCS pins

   For each approved drift event, update the stored pin from the old digest to
   the JCS digest emitted by v1.2.1 and later.

   ```diff
   -        add: <old-json-dumps-digest>
   +        add: <new-rfc8785-jcs-digest>
   ```

   For pins in `config.yaml`, `mcp-hangar pin --check --config config.yaml`
   connects to each server and lists every pin that disagrees with what the
   server serves (`drift math.add`, with the pinned and the serving digest), and
   exits 1 if any does. Once you have reviewed them, `mcp-hangar pin --write`
   writes the serving digests into the file and keeps the previous one as
   `config.yaml.bak`. It writes every observed digest, so review before you run
   it.

1. Fix malformed tool entries before returning to `block`

   Since v1.2.1, Hangar rejects tool entries where `name` is missing, empty, or
   not a string. If a server emits one of these, fix the MCP server schema
   instead of pinning around the error.

   Bad examples:

   ```json
   {"description": "missing name"}
   {"name": ""}
   {"name": 123}
   ```

1. Re-enable `block`

   After all reviewed pins are updated and malformed schemas are fixed, switch
   `digest_enforcement` back to `block`.

   Restart Hangar and repeat the same tool calls. There should be no digest
   mismatch events in the log.

   ```bash
   docker exec hangar-1.3-cookbook sh -lc '
     grep -E "DigestMismatchEvent|digest.*mismatch|unknown.*digest" \
       /tmp/hangar-1.3-digest.log || true
   '
   ```

   Expected output: no lines.

1. Stop the smoke-test container

   ```bash
   docker rm -f hangar-1.3-cookbook
   ```

## What Just Happened

v1.2.1 made digest computation deterministic across runtimes by using RFC 8785
JCS before SHA-256 hashing. That is stricter and more portable than relying on
Python `json.dumps` output, but it means old pins from v1.2.0 and earlier may not
match the same tool schema after upgrade. This behavior is unchanged in the
current release.

v1.2.1 also avoids false drift from optional empty values. These are now treated
as absent during digest computation:

- `None`
- `{}`
- `[]`
- `""`

This prevents two otherwise equivalent servers from producing different digests
only because one omits an optional field while another sends it empty.

The `allow_degraded` name was also retired in v1.2.1, in the
`DigestUnknownPolicy` type. The helper that maps the old string to
`allow_unverified` with a `DeprecationWarning` is still in the package, but no
configuration reaches it: a configured pin is enforced in its server's
`digest_enforcement` mode, and a tool with no pin is not digest-checked at all.

## Key Config Reference

| Setting | Use |
| ------- | --- |
| `tool_projection.digest_enforcement: audit` | Allow calls and record digest drift during migration |
| `tool_projection.digest_enforcement: warn` | Allow calls and emit warnings during migration |
| `tool_projection.digest_enforcement: block` | Reject unapproved digest drift after migration. The default |
| `tool_projection.pins` | `{tool name: digest}`; the digest is 64 lowercase hex characters |
| `allow_unverified` | Python API only (`DigestUnknownPolicy`); not a config key |
| `allow_degraded` | Deprecated alias of `allow_unverified` in the Python API; not a config key |

## What's Next

Keep `/interceptors/list` clients up to date. Since v1.2.1, Hangar returns two
distinct interceptor names; since 2.0.0 they are `io.mcp-hangar.validator` and
`io.mcp-hangar.mutator`. See
[15 -- Interceptor Discovery](15-interceptor-discovery.md).

For the full background, see
[Interceptor Framework](../architecture/INTERCEPTOR_FRAMEWORK.md) and
[Upgrade Guide](../upgrade.md).
