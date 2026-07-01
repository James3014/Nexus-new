# LocalModel Sprint C9 Single Candidate Isolation

**Status**: `LOCAL_MODEL_SPRINT_C9_SINGLE_CANDIDATE_ISOLATION_COMPLETE`

**Date**: 2026-06-30

**Commit**: `593b6d467 wire LocalHeal output and candidate closure contracts`

## Files Changed

| File | Property |
|------|----------|
| `nexus/services/local_heal/local_model_executor.py` | candidate isolation gate, isolated workspace apply, isolated verifier |
| `tests/unit/local_heal/test_local_model_executor.py` | C9 candidate projection and isolation tests |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | seam truth assertion update |

## Candidate Projection Contract

- Only non-empty `pipeline_final_patch` projects to candidate
- Empty patch keeps empty candidate hash (`empty_hash`)
- Candidate hash must be non-empty for isolation to proceed
- `pipeline_result_projected = True` only when `pipeline_final_patch` is non-empty and non-whitespace

## Isolation Contract

- Candidate must be applied in isolated workspace via `run_isolated_workspace_apply`
- Selected candidate hash must match applied patch hash (`hash_match = selected_candidate_hash_matches_applied`)
- Verifier must run via `run_isolated_verifier`
- `CandidateIsolationReceipt` aggregates apply + verify results
- `candidate_isolation_to_hybrid_route` produces `hybrid_route`

## Solved Contract

- `solved = false` unless ALL of:
  - `pipeline_solve_eligible = True`
  - `hybrid_route is not None`
  - `hybrid_route.route_mode == "local_only_executed"`
- Empty pipeline patch → `solved = false` (no candidate projected)
- Hash mismatch → `solved = false`
- Verifier fail → `solved = false`

## Test Command

```bash
/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_downstream_enforcement_gates.py \
  tests/unit/local_heal/test_capability_adapter.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_localheal_pipeline_seam_truth.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py \
  tests/unit/local_heal/test_committee_route_trace.py \
  -q
```

**Observed result**: 122 passed, 11 warnings

## Explicit Statements

- **Unit/focused-tested only**: All C9 tests mock the isolation/verifier chain. No live Ollama execution tested.
- **Live M1 evidence still required**: Live M1 must prove `pipeline_final_patch_len > 0`, `candidate_isolated = true`, and `verifier_result = pass` in real execution. Current M1 row shows `pipeline_final_patch_len = 0`.
- **Solved not claimed**: `solved = false` in unit tests when isolation/verifier is not mocked to pass. Live M1 row must show `solved = true` to claim progress.

## Verification

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py
# Result: pass
```
