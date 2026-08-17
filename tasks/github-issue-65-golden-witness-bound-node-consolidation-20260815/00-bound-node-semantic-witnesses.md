---
artifact_authority: current
task_id: github-issue-65-bound-node-semantic-witnesses
campaign_id: github-issue-65-golden-witness-bound-node-consolidation-20260815
source_issue: "#65"
owner: James Chen
status: ACTIVE
terminal_state: CANDIDATE_PENDING_OWNER_RECONCILIATION
baseline_revision: cdf2570ede5ae218f36f886b696c8da45458043a
reconciled_main: 9296d68fe19d933cb78b9a0470a054ea5efd4c2f
current_main: 9296d68fe19d933cb78b9a0470a054ea5efd4c2f
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

# Bound-node semantic Golden witnesses

## Objective

Make the three already corpus-bound nodes for GB-013, GB-014, and GB-019 carry
the semantic assertions already proven by their merged sibling witnesses.
Keep the bound node names stable and consolidate redundant sibling coverage.

## Inputs and dependencies

- Current main `c75a42279556cd515e8f5d775cecd2ecde7aa301`; prior reconciled
  main `ccd23defe9aa5905d26f34a865746c1eff7d039f`, prior reconciled main
  `586abbfb459550de912002203ff2911c7a40db58` (includes PR #244), and prior
  reconciled main `cdf2570ede5ae218f36f886b696c8da45458043a` (PR #236 merge)
  are retained as historical receipts.
- The semantic sibling witnesses already exist in
  `tests/contracts/test_hybrid_route_contract.py`.
- PR #290 owns the separate GB-042 corpus binding and remains outside this
  slice.
- PR #228 owns corpus/evaluator files and remains outside this slice.
- Fresh overlap audit found no open PR owning the allowed implementation file.

## Allowed implementation/test files

- `tests/contracts/test_hybrid_route_contract.py`

This card and INDEX are governance artifacts outside the one-file
implementation ceiling. Maximum PR scope is three files total. No deletions.

## Required behavior

- `test_hybrid_route_default_values` must remain the bound GB-013 node and
  exercise the relevant fail-closed/default authority semantics, not merely
  field presence.
- `test_to_dict_round_trip` must remain the bound GB-014 node and prove the
  semantic serialization/round-trip contract, including authority-safe
  defaults.
- `test_advisory_guard_cannot_block_delivery_yet` must remain the bound GB-019
  node and exercise the public delivery seam: advisory verifier failure cannot
  block delivery or create retry/block/claim transition, while the deliberate
  fail-closed override remains distinct.
- Consolidate or remove only redundant sibling test bodies in the same file;
  preserve all behavior and bound node names.
- Unknown, malformed, or authority-conflicting inputs remain fail closed.

## Forbidden scope

No changes to corpus mappings, evaluator, workflow, production source,
CapabilityPlanner, Router, Workforce, lifecycle, claim, approval, integration,
merge, release, or production authority. Do not touch PR #228, PR #290, #143,
or any other file.

## Verification

- Run the three exact bound nodes plus the adjacent GB-019 negative witness.
- Run the full `tests/contracts/test_hybrid_route_contract.py` module.
- Run the canonical Golden evaluator for GB-013, GB-014, and GB-019 when the
  existing selector supports exact case selection; do not change the evaluator
  to make this pass.
- Run Ruff on the changed test file and `git diff --check`.
- Prove exact three-file PR scope and zero deletions.
- Independent hostile review is required before any merge request.

## Exit

Issue #65 bound-node semantic witness Candidate PR only. This does not close
Issue #65, does not merge PR #290, and does not resolve GB-073 or other residual
Issue scope.

Claim ceiling:
`GOLDEN_WITNESS_BOUND_NODE_SEMANTICS_CANDIDATE_ONLY`.

## Candidate reconciliation (2026-08-16)

This card is a reconciliation candidate pending Owner terminal disposition.
The historical contract above is preserved as the implementation baseline.

- Physical merge: PR #297 merged as
  `f507199466d6a87dfec4b145df0211e8a3aa3904`, an ancestor of current main
  `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`.
- Historical receipts retained: prior reconciled mains
  `c75a42279556cd515e8f5d775cecd2ecde7aa301`,
  `ccd23defe9aa5905d26f34a865746c1eff7d039f`,
  `586abbfb459550de912002203ff2911c7a40db58`, and
  `cdf2570ede5ae218f36f886b696c8da45458043a` (PR #236 merge); PR #290 owns
  the separate GB-042 corpus binding and merged as
  `63becf8462eb1f28bf8e143139157ce82318a07d`.
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
