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
