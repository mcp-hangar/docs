---
title: Upgrade Guide
---

This guide covers user-visible migration steps between MCP Hangar releases.

## Upgrade to 1.3.0

MCP Hangar 1.3.0 relicenses the project to MIT, folds the former enterprise
package into the main `mcp_hangar` package, and tightens digest-pinning
canonicalization.

### Recompute pinned tool digests

`compute_tool_digest()` now uses RFC 8785 JSON Canonicalization Scheme (JCS)
instead of `json.dumps` output. Existing pinned digests produced by earlier
versions may no longer match and must be regenerated before enforcement mode is
enabled.

When recomputing digests, note the v1.3 normalization rules:

- `None`, `{}`, `[]`, and `""` are treated as absent values.
- Tool entries with a missing, empty, or non-string `name` field are rejected.

Recommended rollout:

1. Upgrade one environment with digest enforcement set to `audit` or `warn`.
2. Collect the new expected digests from the audited tool inventory.
3. Replace old pins with the RFC 8785/JCS digests.
4. Re-enable `block` only after the audited drift is resolved.

### Rename `ALLOW_DEGRADED` to `ALLOW_UNVERIFIED`

`DigestUnknownPolicy.ALLOW_DEGRADED` was renamed to
`DigestUnknownPolicy.ALLOW_UNVERIFIED` for clarity.

If your YAML or code uses the string value `allow_degraded`, change it to
`allow_unverified`. MCP Hangar 1.3 still accepts `allow_degraded` with a
`DeprecationWarning`; support is scheduled for removal in v1.4.

### Remove license-tier assumptions

The former BSL/enterprise split is gone. All MCP Hangar features are now
available under the MIT license.

Required cleanup for integrations and deployment manifests:

- Stop setting `HANGAR_LICENSE_KEY`; v1.3 ignores it and emits a
  `DeprecationWarning` when present.
- Remove checks for `LicenseTier`, `LicenseValidation`, or
  `ApplicationContext.license_tier`.
- Update imports that referenced the former `enterprise/` package; auth,
  compliance, approvals, integrations, and persistence modules now live under
  `src/mcp_hangar/`.

### Verify interceptor discovery clients

`interceptors/list` now returns unique instance names required by SEP-1763:

- `mcp-hangar-validator`
- `mcp-hangar-mutator`

If a client keyed both entries by the previous shared name `mcp-hangar`, update
it to handle the two explicit instance names.
