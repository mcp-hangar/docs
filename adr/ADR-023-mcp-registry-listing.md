# ADR-023: The MCP Registry Entry Describes a Package, Not a Service

**Status:** Accepted
**Date:** 2026-08-16
**Authors:** MCP Hangar Team
**Related:** core `server.json`, core `.github/workflows/release.yml` (`publish-registry`), [ADR-010](ADR-010-retire-agent-cloud-tier.md) (no hosted tier).

## Context

The Official MCP Registry (`registry.modelcontextprotocol.io`) is the upstream every aggregator reads -- Glama, PulseMCP, mcp.so, mcptoplist all ingest from it rather than from a submission form. Hangar was in none of them because it was in none of it: a search for `hangar` returned zero servers. Their rankings weight listing age and version count, both of which only start accruing once an entry exists, and Hangar's release cadence is the one input we already have plenty of.

An entry is identified by its name. Renaming it later does not move the listing, it creates a second one and resets the age of the first, so the namespace is a one-time decision.

## Decision

### 1. The name is `io.mcp-hangar/hangar`, proved by DNS

The namespace matches the domain and the brand. Ownership is proved with an Ed25519 key whose public half lives in a TXT record on the apex of `mcp-hangar.io`, and `mcp-publisher login dns` signs with the private half.

The alternative, `io.github.mcp-hangar/*` via GitHub OIDC, needs no key material at all and is operationally cheaper. It was not taken because it puts GitHub in the name of the product. It remains the documented fallback -- at the price of a new entry and a reset listing age, which is why it is a decision for a human and not a CI failure mode.

### 2. The entry describes the PyPI distribution over stdio, and declares no `remotes`

`packages[0]` is the `mcp-hangar` PyPI distribution, started as `mcp-hangar` with no arguments -- which is the stdio server -- with `MCP_CONFIG` declared as an optional filepath.

There is deliberately no `remotes` block. A `remotes` entry is a URL a client connects to, and Hangar has no hosted instance and will not have one. The absence is the honest statement, not an omission to be fixed: the registry entry is how someone installs Hangar, never where it runs.

HTTP is not described either. The `--http` mode binds a host and port the operator chooses, and a registry `url` template can only reference variables declared in the same entry -- so the only truthful HTTP entry would be one that asks the reader for the address of a gateway they have already deployed, which is not an installation.

### 3. Publishing rides the release, after PyPI

The registry proves package ownership by fetching the PyPI metadata for exactly the version in `packages[0].version` and scanning the README that PyPI serves for `mcp-name: io.mcp-hangar/hangar`. That artifact does not exist until the release workflow has uploaded it, so the publish is a job in that workflow gated on `needs: [publish-pypi]` rather than a separate tag-triggered workflow racing it.

Stable releases only. PyPI serves a prerelease under its PEP 440 spelling (`2.5.0rc1`) while `server.json` carries the semver spelling release-please writes (`2.5.0-rc.1`), so the ownership fetch would 404 -- and a prerelease in a discovery registry is noise regardless.

### 4. The key is an environment secret behind a required reviewer

`MCP_PRIVATE_KEY` authorises publishing anything under `io.mcp-hangar/*`, so it lives on the `mcp-registry-publish` environment -- restricted to `v*` tags, with a required reviewer -- and never as a repository or organisation secret. Each release therefore pauses for an explicit approval before it publishes. That pause is the point.

## Consequences

**A rename is a new product as far as the aggregators are concerned.** Anything that changes `name` -- including the OIDC fallback -- forfeits the listing age this ADR exists to start accruing.

**Three couplings can only fail at release time, so they are tested before it.** The README marker must match `server.json`'s name, and both version fields must match `pyproject.toml`; a unit test asserts all three, because the registry rejects a re-publish of a version it already holds and the mistake cannot be corrected for that release.

**The registry is in preview.** Upstream reserves the right to reset data before GA. The recovery is a re-publish through the same flow with the same name and key; the listing age at the aggregators would not survive it.

**A container entry stays open.** A second `packages[]` element of type `oci` becomes worth adding once the published image has a sensible standalone invocation (core#961).
