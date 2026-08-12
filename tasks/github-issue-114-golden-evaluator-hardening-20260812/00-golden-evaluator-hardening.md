# Task Card: Issue 114 Golden Evaluator Hardening

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

## Goal

Make Golden evaluator evidence revision-bound:
- exact node collection validation;
- additive provenance binding;
- per-case witness evidence map;
- remove evaluator-only permanent case ceiling;
- add push-to-main backstop without duplicate schedule.

## Verification

- focused Golden evaluator tests
- workflow syntax validation
- git diff --check
