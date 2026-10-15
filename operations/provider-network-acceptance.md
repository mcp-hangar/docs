# Provider network acceptance

Use this procedure to assess the ADR-013 boundary on a specific deployment.
A successful CI run or an applied NetworkPolicy does not establish that boundary
on another cluster. Keep the result **NOT RUN** until the probes below finish.

## Review and release evidence

[Operator release v0.17.30](https://github.com/mcp-hangar/mcp-hangar-operator/releases/tag/v0.17.30)
contains the Audit backstop correction and opt-in provider ingress isolation.
The merged [operator #348 CNI matrix](https://github.com/mcp-hangar/mcp-hangar-operator/actions/runs/38726923571)
passed on Calico, Cilium and Cilium with NodeLocal DNSCache. Its ingress scenario
checks gateway allow, ordinary client deny, matching labels in the wrong
namespace deny, wrong labels in the gateway namespace deny, and opt-out.
These are disposable CI topologies, not production acceptance.

Use a chart whose `appVersion` contains the feature. If `image.tag` overrides it,
verify the actual image and both provider-ingress flags. Review the operator's
upgrade notes for Audit/default-Allow behavior before changing a deployment.

## Prepare the deployment record

Record all of the following before requesting approval to run the test:

- Kubernetes context, cluster version, CNI/version and DNS topology.
- Operator chart version, values, image digest and running arguments.
- Gateway namespace, actual pod labels, selected gateway pods and source IPs.
- Test MCPServer namespace/name, provider pod labels/IP and listener port.
- Every NetworkPolicy and CiliumNetworkPolicy selecting the provider or probe.
- Expected gateway health checks and provider health/readiness behavior.
- Existing ingress annotation, egress policy mode/defaultAction and rollback values.

The ingress builder allows TCP/8080. Verify that this matches the test provider's
actual listener; do not infer the port from a Service's external port. Use a
dedicated container-mode MCPServer and dedicated probe pods, with a functioning
listener and known baseline connectivity. Inventory independent policies first:
NetworkPolicy allows are additive, and a provider with egress restrictions may
need its own DNS/upstream configuration for this test.

Do not change a production namespace, operator arguments or MCPServer until the
maintainer approves the named context, target resources and rollback. Prefer a
disposable namespace on the intended CNI; record any difference from production.

## Run the ingress probes

Configure `providerIngress.gatewayNamespace` and the real `hangar.gatewaySelector`.
Keep global `providerIngress.enabled=false`; opt in only the test MCPServer using
`mcp-hangar.io/provider-ingress: "true"`. Wait for reconciliation and record the
owned policy plus `ProviderIngressApplied`, including its reason and generation.
False or Unknown requires investigation, not a passing acceptance result.

For each probe, use a new connection to the provider Pod IP on TCP/8080. With a
probe image that provides BusyBox netcat, execute `nc -z -w 3 <provider-pod-ip> 8080`
inside the selected source pod. Capture the exit code, source identity, destination
and timestamps; a timeout caused by a missing listener or unrelated source egress
deny is inconclusive. Baseline successful connectivity before the fence is needed
to distinguish these cases. Treat unexpected success in a deny case as failure.

| Source | Expected result with opt-in | Recorded result |
| --- | --- | --- |
| Real gateway namespace and matching pod labels | Allow | NOT RUN |
| Ordinary client in provider namespace | Deny | NOT RUN |
| Matching gateway labels in a different namespace | Deny | NOT RUN |
| Wrong pod labels in gateway namespace | Deny | NOT RUN |
| Actual gateway MCP call to the test provider | Success for an allowed operation | NOT RUN |
| Gateway and provider health/readiness checks | Remain healthy | NOT RUN |

Set the test server annotation to `"false"`. Verify removal of only the
operator-owned ingress policy. Repeat the ordinary-client probe: expect baseline
connectivity if no independent policy blocks it. An independent deny must remain
in place; annotate that topology instead of claiming opt-out removed it.
Restore the original annotation after collecting evidence.

## Run Audit and Enforce probes

Use an isolated test target without an independent deny, and a controlled TCP
listener reachable at baseline. Save the MCPEgressPolicy before modifying it.
For each transition, wait for `status.observedGeneration` to match and record
`BackstopApplied`, `BackstopEnforcement`, the generated policy and fresh probes.

| Policy stage | Expected policy-owned behavior | Recorded result |
| --- | --- | --- |
| Audit with default Deny | No blocking backstop; baseline destination reachable | NOT RUN |
| Enforce with default Deny | Destination outside the allow-list blocked | NOT RUN |
| Return to Audit | Owned blocking backstop removed; baseline reachable again | NOT RUN |
| Enforce with default Allow | No policy-owned restrictive backstop | NOT RUN |
| Same Allow stage with a separately owned deny | Independent deny still blocks | NOT RUN |

Also exercise a permitted and a forbidden MCP operation through the configured
gateway in Enforce mode. Use a principal authorized for the operation so that
independent authorization denial cannot masquerade as an egress-policy result.
Capture the protocol result and corresponding policy
and audit/decision evidence. Repeat the forbidden operation in Audit mode and
verify observation without policy-owned blocking. TCP reachability alone does
not prove an L7 rule was evaluated. Use the deployment's existing authenticated
client; redact credentials and sensitive tool arguments from the evidence.

## Qualifying limits and rollback

Record node/host traffic, pre-existing connections, other additive allow policies,
remote providers and opted-out servers as unverified unless separately exercised.
Do not extend a result for container pods to remote endpoints. NodeLocal DNS and
Cilium hostname egress require their own allowed/denied DNS and upstream probes;
the ingress test does not qualify hostname egress.

Restore the saved test policy, annotation and operator values; remove only the
named probe resources. Verify gateway/provider health and that independently
owned policies are unchanged. Retain before/after manifests and probe evidence.

Attach the completed record to [docs #471](https://github.com/mcp-hangar/docs/issues/471).
Report PASS, FAIL or INCONCLUSIVE per row and identify every untested boundary.
Closing the architecture follow-up requires a maintainer decision on the retained
ADR boundary and acceptance evidence for the deployment scope being claimed.
