# Report - C15-5G Live Committee Bridge Validation

This report documents the live validation results of the small-model committee executor bridge.

## C15-5F Commit Hashes
- **Runtime and Tests Commit**: `063a06329`
- **Learning Closure Commit**: `229648c69`

## C15-5G Benchmark Configuration
- **Command**:
  ```bash
  /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py \
    --task-id toy-math-verifier-evidence-gap \
    --executor-model qwen2.5-coder:7b-instruct \
    --delegated-retry-candidate-models ornith:9b,qwythos:9b,qwen2.5-coder:7b-instruct
  ```
- **Timeout settings**: Outer timeout: 720s, Provider timeout: 240s
- **Model list**: `ornith:9b`, `qwythos:9b`, `qwen2.5-coder:7b-instruct`

## Latest JSONL Row Summary
- **task_id**: `toy-math-verifier-evidence-gap`
- **delegated_retry_committee_path_used**: `True`
- **delegated_retry_committee_candidate_count**: `3`
- **delegated_retry_committee_winner_model**: `""` (No winner selected)
- **selected_candidate_hash**: `85f262c12f59f2a05f8de4eb31896c813a7942e100bdfca13f0d41f8161469d4` (First attempt patch hash)
- **selected_candidate_hash_matches_applied**: `False` (Retry failed, fallback did not run)
- **verifier_result**: `fail`
- **solved**: `False`
- **solve_mechanism**: `delegated_retry_unresolved`
- **duration_sec**: `311.94s`

## Candidate-Level Table

| Proposer Model | Raw Output Excerpt | Format Class | Conversion Status | Apply Status | Candidate Hash | Isolated Verifier Result | Selected | Rejection Reason | Candidate Classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ornith:9b` | `""` | `EMPTY` | `none` | `empty_patch` | `""` | `fail` | `False` | `patch_empty` | `MODEL_LOAD_FAILED` |
| `qwythos:9b` | `""` | `EMPTY` | `none` | `empty_patch` | `""` | `fail` | `False` | `patch_empty` | `EMPTY_PATCH` |
| `qwen2.5-coder:7b-instruct` | `--- a/toy/math_util.py...` | `UNIFIED_DIFF` | `none` | `format_rejected` | `666f445e...` | `fail` | `False` | `unified_diff_malformed` | `UNIFIED_DIFF_CONVERSION_FAILED` |

## Telemetry & Validation Audit
- **Did converted unified diff reach isolated apply?**: No. The only model that produced a unified diff (`qwen2.5-coder`) failed the conversion due to a malformed diff format (`unified_diff_malformed`), and was correctly blocked from apply.
- **Did isolated verifier run per candidate?**: No. All candidates were rejected before isolated verifier check.
- **Did any candidate pass verifier?**: No.
- **Selected winner or no-winner reason**: No winner was selected because all three models in the committee failed to produce a valid, verifiable patch.
- **Solved status**: `solved = NOT_PROVEN`

## Overall Status
**`C15_5G_BRIDGE_CONVERSION_FAILED`**

## Next Task
**C15-5H: Live Committee Solve with Valid Unified Diff Conversion**
Verify the end-to-end committee path (including isolated apply/verify) by using a candidate model that outputs a valid, successfully convertible unified diff.
