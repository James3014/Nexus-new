# Nexus governance refresh — source-bound, not runtime authority

Revision: 2026-09-08-r1. Basis: uploaded 03 Core Mental Model §1–2 and 09 Collaboration Standard §2026-09-08 reconciliation. These are source observations, not a fresh host/Issue/admission read.

## Repository and execution lane

Determine the exact target repository and read its current root/nested `AGENTS.md` and applicable operating-mode contract. Nexus-new owns governance/collaboration and legacy integration; `nexus-core` owns Evidence Trust + Completion; `nexus-learning` owns evidence-bounded learning; `nexus-open-swe-runtime` owns external execution; DevSpace is independent host/control transport. Do not export a Nexus-new card into another repo as mutation authority without the target contract.

`DIRECT_CANONICAL` is bounded Owner-authorized primary-agent work. Eligible `DIRECT_DELEGATED` is one bounded external worker through an approved non-Nexus plane, independently verified, then STOP. Neither requires a Nexus Task Card solely for mutation or delegation. Use a tracked card when the actual repository/action requires governed authority. Autonomous resident Open SWE work described in #850 explicitly requires a repository-local Git-tracked card, exact Issue contract, allowed paths, verifiers and independent Candidate acceptance. Isolation is necessary when required for safe execution; isolation alone does not mint or choose a Nexus lifecycle.

Existing attempts retain their contract. A governed/NEXUS_GOVERNED attempt must never silently downgrade to direct/OWNER_DIRECT when authority or transport fails. Block, rebind or reconcile. A separately authorized recovery attempt needs a new authority identity, and must not duplicate an unresolved external effect.

## Authority and evidence

CapabilityPlanner remains the sole Nexus route/capability authority. Workforce Admission constrains eligibility, not routing or approval. For a direct non-Nexus lane, use its explicit external identity contract rather than inventing Nexus admission. Models, Learning recommendations, Open SWE and DevSpace never self-mint acceptance, integration, merge or production authority. Keep scope, revision/physical diff, meaningful verification, independent review where required, and claim ceilings intact. Candidate R3 is READY_FOR_OWNER_REVIEW, not an automatic global policy replacement. Do not enable AUTO_CHAIN from a historical or Candidate paragraph; preserve the active explicit contract and stop boundary.

## Exact external-effect identity

Before a first possible effect, bind the exact logical effect/operation/session and request identity through the governing surface. Match target `operation_id` on result, continuation and reconciliation; workspace indexes are projections only. A local lookup miss, empty session list, process death or provider-call count is not authoritative remote absence. `OUTCOME_UNKNOWN != retry permission`: reconcile the same effect, do not blindly resend or switch provider. Missing/malformed observed provider/model attestation must not be filled from expected configuration. Do not invent public-schema fields; if the actual surface cannot express or prove a necessary binding, report its capability gap.

## Claim ceilings

Producer fix != consumer fix != deployment != runtime witness != independent acceptance. Source merge, healthy transport, test PASS and old closed gates are not interchangeable. Resolve current facts from exact evidence, business semantics from approved decisions, and unresolved conflicts from the responsible authority, not model preference.

Load the dated state/workforce references only when relevant. The package source hashes identify documents, not authenticity or authorization.
