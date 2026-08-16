---
artifact_authority: current
task_id: github-issue-65-gate-b-shape-default-witnesses
campaign_id: github-issue-65-golden-witness-gate-b-20260813
source_issue: "#65"
owner: James Chen
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
baseline_revision: 80370ab3c5e3c3714cf378de1dba90412d1a2a7f
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
readiness_marker: GOLDEN_WITNESS_SEMANTIC_HARDENING_PROVEN
claim_ceiling: GOLDEN_WITNESS_SEMANTIC_HARDENING_PROVEN_ONLY
commit_required: true
candidate_required: true
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
authorized_deletions: []
---

# Issue #65 Gate B — Semantic shape/default witnesses

## Objective

Strengthen Gate B witnesses `GB-013`, `GB-014`, `GB-021`, `GB-025`,
`GB-061`, `GB-081`, and `GB-082` with behavioral positive assertions and
applicable negative/tamper controls. Evidence must observe route, admission,
read-model, policy-lane, or authority behavior rather than only enum values,
defaults, serialization shape, wording, fixture counts, or flags.

## Baseline and scope

- baseline: `80370ab3c5e3c3714cf378de1dba90412d1a2a7f`
- Gate A is physically merged at this baseline.
- test-only; `AUTO_CHAIN=false`; maximum files: 7; no deletions.

Allowed files:

- `tests/contracts/test_hybrid_route_contract.py`
- `tests/contracts/test_workforce_admission_contract.py`
- `tests/contracts/test_claim_evidence_read_model.py`
- `tests/ops/test_policy_lane_gate.py`
- `tests/golden_behavior/test_corpus.py`
- this Task Card
- this campaign's `INDEX.md`

## Required behavior

- Hybrid defaults/round trips remain non-claiming and reject a hostile
  authority or production/public-claim escalation.
- Workforce decisions use the typed admission vocabulary and reject forged or
  malformed decisions while preserving fail-closed reasons and identity.
- Claim read-model PASS remains observational and cannot authorize runtime,
  benchmark, public claim, approval, integration, or release; missing/tampered
  binding fails closed.
- Policy Lane fixtures prove behavior against the authoritative manifest and
  fail when a hard-lane requirement or identity is removed/substituted.
- Workforce preference text remains downstream guidance; a hostile routing or
  authority directive is detected rather than accepted as mere wording.

## Forbidden

- no production, corpus, evaluator, workflow, docs, manifest, lifecycle,
  route, Workforce policy, approval, integration, release, or public claim
  mutation;
- no edits for Gate C, #143, or #191;
- if a semantic witness exposes a production defect, stop that slice and
  report it; do not weaken the test.

## Verification

- exact mapped tests and the five affected test modules;
- canonical Golden evaluator on the exact Candidate head with findings excluded;
- Ruff check/preview format for changed Python files;
- `git diff --check`, seven-file scope, zero deletions.

## Exit

Stop at a scoped Candidate PR pending independent false-green review. Maximum
claim: `GOLDEN_WITNESS_GATE_B_SEMANTIC_TESTS_CANDIDATE_ONLY`.

## Terminal reconciliation (2026-08-16)

This card is terminal. The historical contract above is preserved as the
implementation baseline.

- Physical merge: PR #231 merged as
  `a74d838cc6bb14af47ce79207181c12a1aed1d35`, an ancestor of current main
  `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; Gate A (PR #227) merged as
  `80370ab3c5e3c3714cf378de1dba90412d1a2a7f` on the historical baseline.
- Final evidence: 17/17 golden cases, 20/20 semantic witnesses,
  `findings_included_in_eval=false`, evaluation report SHA256
  `f3a65fadcc6f88449d99c3ef333e599225099874039783162a51fbaa0deb50fd`.
- Marker: `GOLDEN_WITNESS_SEMANTIC_HARDENING_PROVEN`; ceiling
  `GOLDEN_WITNESS_SEMANTIC_HARDENING_PROVEN_ONLY` (repository-contained
  source/test/governance evidence only). `AUTO_CHAIN=false`.
- No runtime, route, Workforce, provider, approval, integration, merge,
  release, or production authority is granted by this reconciliation; no
  #143 or #191 work.
