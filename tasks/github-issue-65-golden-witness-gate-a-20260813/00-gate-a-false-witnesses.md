---
artifact_authority: current
task_id: github-issue-65-gate-a-false-witnesses
campaign_id: github-issue-65-golden-witness-gate-a-20260813
source_issue: "#65"
owner: James Chen
status: ACTIVE
terminal_state: CANDIDATE_PENDING_OWNER_RECONCILIATION
baseline_revision: 727efaac9a354748a50946b7012c8847afea6ded
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
readiness_marker: GOLDEN_WITNESS_SEMANTIC_HARDENING_CANDIDATE_PENDING_OWNER_RECONCILIATION
claim_ceiling: GOLDEN_WITNESS_SEMANTIC_HARDENING_CANDIDATE_ONLY
commit_required: true
candidate_required: true
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
authorized_deletions: []
---

# Gate A semantic Golden witnesses

## Objective

Replace GB-019 and GB-042 false/insufficient witnesses with behavioral positive
and negative evidence only. Do not change production or corpus claims.

## Inputs and dependencies

- #7 M3-B/M3-D physically merged and #7 closed.
- corpus blob `88a236e3e440052e193aed08f19e996ddab7ed5a`.
- GB-019 witness blob `4d417fe6c1de4c9fb976b55db7c7c1eec4ff991e`.
- GB-042 witness blob `f88dba4950cfb606414a83b841ff6a43b4b1a59d`.

## Allowed implementation/test files

- `tests/contracts/test_hybrid_route_contract.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

This card and INDEX are governance artifacts outside the two-file ceiling.

## Required behavior

- GB-019 exercises the public delivery seam: advisory guard plus failing
  verifier cannot block delivery or create retry/block/claim transition;
  blocking/non-advisory override fails closed.
- GB-042 uses a fully valid external-acceptance and approval/integration
  binding; calling approved integration twice produces one physical side
  effect, stable receipt/commit identity, and idempotent duplicate result.
- If either test exposes a production defect, stop that slice and report a
  separate bounded product Issue; never weaken the witness.

## Forbidden scope

No production, corpus, evaluator, workflow, route/Workforce/lifecycle authority,
Candidate approval semantics, #143, or #191 work.

## Verification

- run the exact GB-019/GB-042 nodes and adjacent focused tests
- canonical Golden evaluator for affected cases if selectable
- Ruff on changed tests and `git diff --check`
- independent hostile review

## Exit

Gate A Candidate PR only. Gates B/C remain residual Issue #65 scope.
Claim ceiling: `GOLDEN_WITNESS_GATE_A_SEMANTIC_TESTS_CANDIDATE_ONLY`.

## Candidate reconciliation (2026-08-16)

This card is a reconciliation candidate pending Owner terminal disposition.
The historical contract above is preserved as the implementation baseline.

- Physical merge: PR #227 merged as
  `80370ab3c5e3c3714cf378de1dba90412d1a2a7f`, an ancestor of current main
  `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`.
- Input witness blobs retained historically: corpus
  `88a236e3e440052e193aed08f19e996ddab7ed5a`; GB-019 witness
  `4d417fe6c1de4c9fb976b55db7c7c1eec4ff991e`; GB-042 witness
  `f88dba4950cfb606414a83b841ff6a43b4b1a59d`.
- Closure evidence asserted only (ASSERTED_UNBOUND_PENDING_RECEIPT): 17/17
  golden cases, 20/20 semantic witnesses, `findings_included_in_eval=false`,
  report SHA256
  `f3a65fadcc6f88449d99c3ef333e599225099874039783162a51fbaa0deb50fd`. No
  repository/GitHub immutable report artifact was located, so this is not
  presented as completion evidence.
- Marker: `GOLDEN_WITNESS_SEMANTIC_HARDENING_CANDIDATE_PENDING_OWNER_RECONCILIATION`; ceiling
  `GOLDEN_WITNESS_SEMANTIC_HARDENING_CANDIDATE_ONLY` (repository-contained
  candidate evidence only; no terminal proof). `AUTO_CHAIN=false`.
- No runtime, route, Workforce, provider, approval, integration, merge,
  release, or production authority is granted by this reconciliation; no
  #143 or #191 work.
