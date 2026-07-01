# LocalModel Sprint C7/C9 Combined Closeout Report

**Status**: `LOCAL_MODEL_SPRINT_C7_C9_OUTPUT_AND_CANDIDATE_CLOSEOUT_COMPLETE`

**Date**: 2026-06-30

## Why Combined

C7 output classification recovery and C9 single candidate isolation share the same file
(`local_model_executor.py`) in a contiguous B3 block (lines 537-615). The C7 telemetry
extraction (pipeline_result_ctx fields) feeds directly into the C9 isolation receipt and
hybrid_route computation. Splitting these into separate commits would require duplicating
the raw_meta construction or introducing an artificial intermediate state. The combined
commit is the correct closeout for this code shape.

## Files Changed

| File | Section | Property |
|------|---------|----------|
| `nexus/services/local_heal/phases/patch_synthesis.py` | C7 | output classification observational fields |
| `nexus/services/local_heal/local_model_capability_executors.py` | C7/C8 | field extraction from pipeline_result_ctx |
| `nexus/services/local_heal/pipeline.py` | C7 | sync_from_v2 unconditional setattr for dynamic attrs |
| `nexus/services/local_heal/local_model_executor.py` | C9 | candidate isolation gate, isolated workspace apply, isolated verifier |
| `tests/unit/local_heal/test_local_model_executor.py` | C7/C8/C9 | all output, quarantine, and isolation tests |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | C9 | seam truth assertion update |

## Test Commands

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

## C7: Output Classification Recovery

### Properties

- Output classification is **observational only**
- No output-class early return in patch_synthesis.py
- No parser/apply behavior change
- No sanitizer added
- No fence stripping added
- `apply_res.preflight_telemetry` is preserved and merged (not overwritten)
- C7 does not change candidate or solved outcome

### Fields Added

| Field | Source |
|-------|--------|
| `output_hash` | SHA-256 of model output |
| `output_class` | EMPTY / REFUSAL / VALID_SEARCH_REPLACE / FENCED_SEARCH_REPLACE / UNIFIED_DIFF / MALFORMED_SEARCH_REPLACE / NATURAL_LANGUAGE / UNKNOWN |
| `parser_error_kind` | From SolidSearchReplaceProtocol.parse() |
| `parser_error_message` | From PatchError |
| `contains_search_marker` | Literal `<<<<<<< SEARCH` presence |
| `contains_replace_marker` | Literal `>>>>>>> REPLACE` presence |
| `contains_markdown_fence` | Literal `` ``` `` presence |
| `contains_unified_diff_header` | `--- a/` and `+++ b/` presence |
| `contains_natural_language_only` | True when output_class == NATURAL_LANGUAGE |
| `micro_verify_context_present` | From pipeline_result_ctx (C8 quarantine) |
| `verifier_command_present` | From pipeline_result_ctx (C8 quarantine) |
| `verifier_command_source` | From pipeline_result_ctx (C8 quarantine) |
| `bare_python_rejected` | From pipeline_result_ctx (C8 quarantine) |
| `micro_verify_failure_reason` | From pipeline_result_ctx (C8 quarantine) |

### Explicit Statements

- Parser/apply behavior unchanged: the output classification runs after parser.parse() and before the existing early-return paths. No new control flow branches.
- No candidate/solved claim: C7 fields are telemetry-only. They appear in raw_model_metadata but do not influence pipeline_solve_eligible, candidate_patch, or solved.

## C9: Single Candidate Isolation

### Properties

- `pipeline_final_patch_len > 0` is required before candidate projection
- Empty pipeline patch must not generate non-empty candidate (verified by test)
- Candidate enters isolated workspace via `run_isolated_workspace_apply`
- Selected candidate hash must match applied patch hash (`hash_match`)
- Verifier pass required before solved (`isolated_verifier_status == "pass"`)
- Solved remains false if candidate isolation or verifier fails
- `solved` requires: `pipeline_solve_eligible AND hybrid_route is not None AND hybrid_route.route_mode == "local_only_executed"`

### Contract

1. Pipeline produces non-empty `pipeline_final_patch` → project as candidate
2. Candidate gets SHA-256 hash → `candidate_hash`
3. Candidate enters `IsolatedApplyRequest` → isolated workspace
4. `IsolatedApplyReceipt` provides: `applied_patch_hash`, `candidate_output_isolated`, `selected_candidate_hash_matches_applied`
5. `IsolatedVerifierRequest` runs verifier command in isolated workspace
6. `IsolatedVerifierReceipt` provides: `verifier_status`, `exit_code`
7. `CandidateIsolationReceipt` aggregates → `candidate_isolation_to_hybrid_route` → hybrid_route
8. `solved = pipeline_solve_eligible AND hybrid_route.route_mode == "local_only_executed"`

### Explicit Statements

- Live M1 still required: unit tests mock the isolation/verifier chain. Live M1 must prove `pipeline_final_patch_len > 0` and `candidate_isolated = true` in real execution.
- Solved not claimed: `solved = false` in unit tests when isolation/verifier is not mocked to pass. Live M1 row must show `solved = true` to claim progress.

## Verification Evidence

```bash
# Syntax check
python3 -m py_compile \
  nexus/services/local_heal/committee_orchestrator.py \
  nexus/services/local_heal/local_committee_candidate_provider.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/local_model_executor.py \
  nexus/services/local_heal/phases/patch_synthesis.py \
  nexus/services/local_heal/pipeline.py \
  tests/unit/local_heal/test_committee_route_trace.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_localheal_pipeline_seam_truth.py
# Result: all pass

# Focused pytest
/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_downstream_enforcement_gates.py \
  tests/unit/local_heal/test_capability_adapter.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_localheal_pipeline_seam_truth.py \
  tests/unit/local_heal/test_local_committee_candidate_provider.py \
  tests/unit/local_heal/test_committee_route_trace.py \
  -q
# Result: 122 passed, 11 warnings
```
