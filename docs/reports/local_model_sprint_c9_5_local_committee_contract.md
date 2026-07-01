# LocalModel Sprint C9.5 Local Committee Contract Hardening

**Status**: `LOCAL_MODEL_SPRINT_C9_5_LOCAL_COMMITTEE_CONTRACT_COMPLETE`

**Date**: 2026-06-30

## Files Changed

| File | Property |
|------|----------|
| `nexus/services/local_heal/committee_orchestrator.py` | proposer/judge constraints |
| `nexus/services/local_heal/local_committee_candidate_provider.py` | proposer/judge constraints |
| `tests/unit/local_heal/test_committee_route_trace.py` | single proposer rejection test |
| `tests/unit/local_heal/test_local_committee_candidate_provider.py` | single proposer + judge reuse tests |

## Test Commands

```bash
/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_committee_route_trace.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py \
  -q
```

**Observed result**: All tests pass (included in 122 passed total)

## Proposer/Judge Constraints

| Constraint | Enforced In |
|-----------|-------------|
| At least 2 proposer models | `CommitteeOrchestrator.run()` + `LocalCommitteeCandidateProvider.generate_committee_candidates()` |
| Judge model must not appear in proposer_specs | Both files |
| Proposer models must be distinct (no duplicates) | Both files |
| Each proposer must have model and role | Both files |
| Judge model must be present in signal_snapshot | `CommitteeOrchestrator.run()` |

## Bug Fixed

**Committee provider loop variable reuse**: The original `local_committee_candidate_provider.py` built the `committee_models` list by first appending `(judge_model, "judge", "none")` then iterating `proposer_specs` in a loop. The bug was that the loop variable `model_name` could be overwritten by the last iteration, causing all proposers to appear as the same model in certain edge cases. The fix restructures the validation to run first (checking distinctness, judge separation), then builds `committee_models` from the already-validated `proposer_specs`.

## Explicit Statements

- Committee is downstream executor, not route authority: `CommitteeOrchestrator` runs within the `local_committee_only` topology. It does not select routes, override `CapabilityPlanner`, or change `RouteMode`.
- Judge cannot override verifier: The judge model receives candidate patches and produces a ranking, but `verifier_result` from the isolated verifier chain is the final authority. The judge's ranking feeds into `CommitteeReceipt` but does not bypass `CandidateIsolationReceipt.verifier_result`.
- No router/planner/topology selector added: The committee contract is purely within the existing `local_committee_only` execution path.

## Verification Evidence

```bash
python3 -m py_compile \
  nexus/services/local_heal/committee_orchestrator.py \
  nexus/services/local_heal/local_committee_candidate_provider.py \
  tests/unit/local_heal/test_committee_route_trace.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py
# Result: all pass

/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_committee_route_trace.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py \
  -q
# Result: all pass (included in 122 passed total)
```
