# C6D Winner-vs-Verifier Misalignment Audit Report

**status**: C6D_WINNER_VS_VERIFIER_MISALIGNMENT_AUDIT_PASS
**date**: 2026-07-06
**files changed**: 0 (read-only audit)

## Case Count

- **Audited**: 11 current-proof combinations
- **assertion_or_behavior_mismatch**: 7 combinations (A1, A3, A4, A5, A6, B1, B3, B4)
- **wrong_location_or_target_miss**: 2 combinations (B2, four-model)
- **Total verification_failed**: 10 combinations

## Winner Truth

| Field | Observation |
|---|---|
| `winner_selected` | 10/10 combinations (committee always picks a winner) |
| `apply_status` | 10/10 `applied` (winner's patch always applies) |
| `isolated_verifier_result` | 10/10 `fail` (winner's patch always fails verification) |
| `selected_candidate_apply_hash_match` | 10/10 `true` (hash matches, apply succeeded) |

**Key finding**: Winner always applies successfully but always fails verification. The committee selects for `apply_success`, not `verify_success`.

## Misalignment Evidence

### Q1: Winner's isolated_verifier_result always fail?
**Yes.** 10/10 combinations. No winner passes verification.

### Q2: Non-winner candidates closer to pass?
**No.** Delegated retry candidates show:
- `format_rejected` (unified diff output can't be converted): ~50% of non-winners
- `empty_patch` (no content produced): ~50% of non-winners
- `verifier_result`: 100% `fail` for all non-winners

No non-winner candidate is closer to passing verification than the winner.

### Q3: Judge偏向容易apply的特徵?
**Yes.** The judge selects based on:
1. Which candidate's patch applies cleanly (`apply_status: applied`)
2. Not which candidate's patch fixes the bug (`verifier_result`)

The winner always has `apply_status: applied` but `verifier_result: fail`.

### Q4: selected_candidate_apply_hash_match=true but verifier fail比例?
**100%.** All 11 combinations have `apply_hash_match=true` but `verifier=fail`.

### Q5: semantic_retry_verifier_evidence_injected改善outcome?
**No.** In all cases:
- `semantic_retry_verifier_evidence_injected: false`
- `orchestrator_verifier_evidence_passed_to_retry: false`

The verifier evidence exists in the system but is NOT being injected into retry attempts. The plumbing at `local_model_executor.py:2218-2224` reads `result_ctx._orchestrator_verifier_evidence_passed` but this is always `False` in the current flow.

### Q6: assertion_or_behavior_mismatch集中在特定模型?
**No.** The failure is distributed across all model combinations:
- qwen+deepseek: ✗
- qwen+ornith: ✗
- qwen+qwythos: ✗
- deepseek+ornith: ✗
- deepseek+qwythos: ✗
- ornith+qwythos: ✗
- All triple combinations: ✗
- Four-model: ✗

No specific model is immune to verification failure.

## Retry Evidence

| Field | Value | Implication |
|---|---|---|
| `semantic_retry_verifier_evidence_injected` | `false` (all cases) | Verifier evidence NOT injected into retry |
| `orchestrator_verifier_evidence_passed_to_retry` | `false` (all cases) | Orchestrator evidence NOT passed to retry |
| `retry_available` | `true` (all cases) | Retry mechanism exists |
| `retry_eligible` | `true` (most cases) | Retry is allowed |

**Key finding**: The retry mechanism exists and is eligible, but verifier evidence is not being injected. The evidence is captured but not used.

## Decision

**Next target: `retry evidence use`**

The evidence shows:
1. Verifier evidence IS captured (verifier_stdout_excerpt, verifier_failure_kind)
2. Retry mechanism IS available and eligible
3. But `semantic_retry_verifier_evidence_injected` is always `false`
4. The plumbing exists at `local_model_executor.py:2218-2224` but reads from a source that's always `False`

**Why this is the lowest-hanging fruit**:
- No model changes needed
- No prompt changes needed
- No committee policy changes needed
- Just connect existing evidence to existing retry mechanism

**If connected**: Retry could use verifier feedback (e.g., "normalize_score does not clamp output") to generate better patches in the next attempt.

## Statements

- **Winner-vs-verifier misalignment**: Confirmed. Judge selects for apply_success, not verify_success.
- **Non-winner candidates**: All fail verification. No candidate is closer to pass.
- **Retry evidence**: Exists but not injected. Lowest-hanging fruit for improvement.
- **No code changes**: This is a read-only audit.
- **No production claim**: Only audit findings established.
