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

## Recorded acceptance (2026-11-08)

The lab cluster this record was prepared for was decommissioned, and the
maintainer decided that deployment acceptance for ADR-013 is the CI packet
tests on Calico and Cilium plus the docs `kind-walkthrough` job, scoped as
below. The decision text is on [docs #471](https://github.com/mcp-hangar/docs/issues/471).
The rows that follow record those runs. They establish the boundary on these
disposable topologies; any other cluster still needs its own run of this
procedure.

| Evidence | Topology | What ran |
| --- | --- | --- |
| [Operator e2e reachability, nightly](https://github.com/mcp-hangar/mcp-hangar-operator/actions/runs/42362999947) at operator `e6bfa3c` | kind with `kindest/node:v1.37.0`; Calico v3.28.2, Cilium v1.20.1, and Cilium v1.20.1 with NodeLocal DNSCache as a pod behind a CiliumLocalRedirectPolicy | `TestOperator_ProviderIngress_GatewayOnly`, `TestOperator_AuditEnforceAudit_Reachability`, `TestOperator_EgressPolicyBackstopIsEnforced`, each passed on all three legs |
| [Docs kind walkthrough](https://github.com/mcp-hangar/docs/actions/runs/42522485888) | kind v0.30.0 with `kindest/node:v1.34.0` and its default CNI (kindnet), published charts | `getting-started/kubernetes-quickstart.md` steps 1 to 8, every expectation held |

Selectors in both: the gateway is namespace `mcp-hangar` and pod label
`app.kubernetes.io/name=mcp-hangar`; the provider is pod label
`mcp-hangar.io/provider: <server>` on TCP/8080; every probe is a new TCP
connection from a new pod. The e2e runs the operator built from the commit,
without core, so it does not exercise MCP calls; the walkthrough runs core and
the published operator, so it does.

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
| Real gateway namespace and matching pod labels | Allow | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e) |
| Ordinary client in provider namespace | Deny | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e) and kindnet (walkthrough step 8, `after: blocked`) |
| Matching gateway labels in a different namespace | Deny | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e); NOT RUN on kindnet |
| Wrong pod labels in gateway namespace | Deny | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e) and kindnet (walkthrough step 8; there the gateway and provider share a namespace) |
| Actual gateway MCP call to the test provider | Success for an allowed operation | PASS on kindnet (walkthrough step 8, `add` answers 5 behind the fence); NOT RUN on Calico or Cilium |
| Gateway and provider health/readiness checks | Remain healthy | PASS on kindnet (walkthrough step 8, `MCPServer` Ready after the fence); NOT RUN on Calico or Cilium |

Set the test server annotation to `"false"`. Verify removal of only the
operator-owned ingress policy. Repeat the ordinary-client probe: expect baseline
connectivity if no independent policy blocks it. An independent deny must remain
in place; annotate that topology instead of claiming opt-out removed it.
Restore the original annotation after collecting evidence.

Recorded: opt-out PASS on Calico, Cilium and Cilium with NodeLocal DNSCache
(e2e: the owned policy is removed and the ordinary client connects again);
NOT RUN on kindnet. The e2e namespace holds no independent deny.

## Run Audit and Enforce probes

Use an isolated test target without an independent deny, and a controlled TCP
listener reachable at baseline. Save the MCPEgressPolicy before modifying it.
For each transition, wait for `status.observedGeneration` to match and record
`BackstopApplied`, `BackstopEnforcement`, the generated policy and fresh probes.

| Policy stage | Expected policy-owned behavior | Recorded result |
| --- | --- | --- |
| Audit with default Deny | No blocking backstop; baseline destination reachable | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e stage 0) |
| Enforce with default Deny | Destination outside the allow-list blocked | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e stage 1) and kindnet (walkthrough step 7, `blocked`) |
| Return to Audit | Owned blocking backstop removed; baseline reachable again | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e stage 2) |
| Enforce with default Allow | No policy-owned restrictive backstop | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e stage 3) |
| Same Allow stage with a separately owned deny | Independent deny still blocks | PASS on Calico, Cilium, Cilium with NodeLocal DNSCache (e2e stage 4) |

Also exercise a permitted and a forbidden MCP operation through the configured
gateway in Enforce mode. Use a principal authorized for the operation so that
independent authorization denial cannot masquerade as an egress-policy result.
Capture the protocol result and corresponding policy
and audit/decision evidence. Repeat the forbidden operation in Audit mode and
verify observation without policy-owned blocking. TCP reachability alone does
not prove an L7 rule was evaluated. Use the deployment's existing authenticated
client; redact credentials and sensitive tool arguments from the evidence.

Recorded: on kindnet the walkthrough's step 6 calls a permitted tool (`add`,
answers 5) and a forbidden one (`read_env`, refused with
`EgressPolicyDeniedError` and layer `l7`) through core with an administrator
key, in Enforce mode. The forbidden operation in Audit mode, and the matching
audit and decision records, are NOT RUN.

## Qualifying limits and rollback

Record node/host traffic, pre-existing connections, other additive allow policies,
remote providers and opted-out servers as unverified unless separately exercised.
The recorded acceptance above leaves all of them unverified, along with
hostname (`toFQDNs`) egress outside the Cilium legs and any CNI not named
here. kindnet's egress enforcement holds for the walkthrough's kind version only:
on the hosted runner's kind (`kindest/node:v1.37.0`, pod subnet
`192.168.0.0/16`) the operator's egress tests saw denied destinations get
through while the ingress fence held
([operator run](https://github.com/mcp-hangar/mcp-hangar-operator/actions/runs/42522227476)).
Do not extend a result for container pods to remote endpoints. NodeLocal DNS and
Cilium hostname egress require their own allowed/denied DNS and upstream probes;
the ingress test does not qualify hostname egress.

Restore the saved test policy, annotation and operator values; remove only the
named probe resources. Verify gateway/provider health and that independently
owned policies are unchanged. Retain before/after manifests and probe evidence.

Attach the completed record to [docs #471](https://github.com/mcp-hangar/docs/issues/471).
On the status side, operator releases before the one with
[mcp-hangar-operator#393](https://github.com/mcp-hangar/mcp-hangar-operator/issues/393)
report kindnet's backstop and fence as unenforced although the probes above
show them blocking; status there is not acceptance evidence either way.
Report PASS, FAIL or INCONCLUSIVE per row and identify every untested boundary.
Closing the architecture follow-up requires a maintainer decision on the retained
ADR boundary and acceptance evidence for the deployment scope being claimed.
