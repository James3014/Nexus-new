# Task Card: Issue 114 Golden Evaluator Hardening

## Status

COMPLETE / TERMINAL_RECONCILIATION

- Historical baseline: `c450c75cedbe7679f564d4eaddb7aa351b8aa0ee`
- Reconciled main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- Current main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- Terminal marker: `GOLDEN_EVALUATOR_EVIDENCE_HARDENING_PROVEN`
- Claim ceiling: `GOLDEN_EVALUATOR_EVIDENCE_HARDENING_PROVEN_ONLY`
- AUTO_CHAIN: `false`

## Scope

Allowed:
- scripts/ops/run_golden_behavior_eval.py
- .github/workflows/pytest.yml
- tests/ops/test_golden_behavior_eval.py (new)
- task files for this campaign

Forbidden:
- tests/golden_behavior/corpus.py
- tests/golden_behavior/test_corpus.py
- runtime, route, Planner, Workforce, lifecycle, acceptance authority
- findings semantics changes
- #116 / PR #229 trusted-verifier authority

## Goal

Make Golden evaluator evidence revision-bound:
- exact node collection validation;
- additive provenance binding;
- per-case witness evidence map;
- remove evaluator-only permanent case ceiling;
- add push-to-main backstop without duplicate schedule.

## Implementation evidence

- PR #198 base `c450c75cedbe7679f564d4eaddb7aa351b8aa0ee`; head
  `2008bba49d024b39c037483889646a6841e51f64`; merge
  `5e2e4f9b651582d51df5d02c270fec712d241124`.
- Owner receipt `5264607384`; post-merge push-triggered Golden run
  `31580745921` reached the main-push Golden step on merge SHA `5e2e4f9b` with
  success.
- Current-main readback confirms evaluator collection/provenance/backstop are
  present; frozen #65 corpus files unchanged.

## Verification

- focused Golden evaluator tests
- workflow syntax validation
- git diff --check
