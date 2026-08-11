# ADR-021: A Remote Upstream in the Configuration File Stays Outside the SSRF Policy

**Status:** Accepted
**Date:** 2026-08-11
**Authors:** MCP Hangar Team
**Related:** [ADR-013](ADR-013-egress-policy-enforcement-model.md) (the enforcement plane), core#836 (connect-time pinning, 2.5.0), core#899 (IPv4-mapped forms), core#903 (this decision), core#908.

## Context

Registering a `remote` upstream through the REST API runs `validate_no_ssrf` against the endpoint, and the command handler sets `enforce_ssrf` on the aggregate. That flag installs `_SsrfGuardedTransport`, which re-resolves the hostname on **every** request and connects to a validated address -- the half added in 2.5.0 that closes DNS rebinding, where a name that passed once is later re-pointed at `169.254.169.254` or `10.x`.

`enforce_ssrf` is set in exactly one place, that handler. A `remote` server declared in `config.yaml` never reaches it, so it gets neither half: the endpoint is accepted without validation, and every later connection is an ordinary httpx dial with no policy applied. The same two endpoints that answer `400 ssrf_blocked` from the API start silently from the file.

This was reported three times across two releases as a residual of the 2.5.0 SSRF work. It is not one. The exclusion is deliberate and was argued in a comment on `HttpClientConfig`. What made it look like an oversight is that the comment was the only place it was written down: an operator moving an upstream out of the API and into the file lost two controls with nothing to tell them.

## Decision

### 1. The configuration file stays trusted, and the policy stays off for it

An operator writing `endpoint: http://10.0.0.5:8080/mcp` in their own configuration file has said what they mean. Applying the strict policy there would refuse a private upstream that was chosen on purpose -- which is the normal case for a gateway sitting in the same cluster as its backends -- and would break working deployments on upgrade to enforce a rule about a channel the operator controls.

The API is different in kind. Its input arrives over the network from a principal, and "the caller chose it" is the property the check exists to distrust.

### 2. The difference is stated, per server, at boot

Silence was the actual defect, so silence is what changes. Startup logs one line for each config-file `remote` upstream, naming the server, its endpoint, and which protections do not apply to it. An endpoint written as a private or metadata-adjacent literal -- one the API would have refused outright -- is told so in those words; anything else is told about the connect-time half, which is the one an operator is least likely to have considered.

The question "is this a literal the strict policy refuses?" is asked through `endpoint_is_a_literal_the_strict_policy_refuses`, the same helper the fleet-restore path uses, so the warning cannot drift from the denylist it describes.

### 3. Nothing is refused

A warning, not a refusal. The gateway starts, the upstream registers, and no request path changes. Refusing here would be a breaking change enforcing a rule this ADR has just decided not to apply.

## Consequences

**An operator who wants the policy has a way to get it.** Register the upstream through the REST API instead of the file; that population is checked at registration and re-checked on every connection. This is now something the log says rather than something the source implies.

**The asymmetry is documented rather than inferred.** The next report of this shape has an ADR to disagree with instead of a comment to discover, which is the whole reason this file exists.

**A per-server opt-in remains available and unbuilt.** `enforce_ssrf: true` on a config-file server would let an operator ask for the strict policy on a specific endpoint without changing the default. Nothing needs it yet; it is recorded here so the option is not re-derived from scratch.

**The warning is bounded by the file.** One line per remote upstream per boot, not throttled, because the set cannot grow at runtime.
