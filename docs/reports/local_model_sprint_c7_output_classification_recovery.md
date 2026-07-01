# LocalModel Sprint C7 Output Classification Recovery

**Status**: `LOCAL_MODEL_SPRINT_C7_OUTPUT_CLASSIFICATION_RECOVERY_COMPLETE`

**Date**: 2026-06-30

**Commit**: `593b6d467 wire LocalHeal output and candidate closure contracts`

## Files Changed

| File | Property |
|------|----------|
| `nexus/services/local_heal/phases/patch_synthesis.py` | observational output classification fields |
| `nexus/services/local_heal/local_model_capability_executors.py` | field extraction from pipeline_result_ctx |
| `nexus/services/local_heal/pipeline.py` | sync_from_v2 unconditional setattr for dynamic attrs |
| `tests/unit/local_heal/test_local_model_executor.py` | C7/C8 output classification and quarantine tests |

## Output Classification Fields

| Field | Source |
|-------|--------|
| `output_hash` | SHA-256 of model output |
| `output_excerpt_first_500` | First 500 chars of model output |
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

- **Observational only**: Output classification runs after parser.parse() and before existing early-return paths. No new control flow branches.
- **No parser/apply behavior change**: The parser still parses the same way. The apply logic still applies the same way. C7 only adds telemetry fields.
- **No sanitizer / no fence stripping**: Fenced output is classified as `FENCED_SEARCH_REPLACE` but fences are not stripped. The classification is a label, not an action.
- **Does not claim candidate or solved progress**: C7 fields appear in `raw_model_metadata` but do not influence `pipeline_solve_eligible`, `candidate_patch`, or `solved`.

## Verification

```bash
python3 -m py_compile \
  nexus/services/local_heal/phases/patch_synthesis.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/pipeline.py
# Result: all pass
```
