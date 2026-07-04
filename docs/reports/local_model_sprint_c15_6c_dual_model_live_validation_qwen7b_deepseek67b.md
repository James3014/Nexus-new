# C15-6C: Dual-Model Live Validation (Qwen 7B + DeepSeek 6.7B)

**Date**: 2026-07-04  
**Status**: `DUAL_MODEL_WIRING_LANE_PARTIAL_PROVEN`

## 1. Task

```text
Run a live dual-model committee validation using:
- qwen2.5-coder:7b-instruct
- deepseek-coder:6.7b-instruct

Target:
prove real dual-model candidate execution on the Nexus path, then inspect
whether solve-lane evidence is strong enough.
```

## 2. Command

```bash
uv run python scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-verifier-evidence-gap \
  --executor-model qwen2.5-coder:7b-instruct \
  --primary-proposer-model qwen2.5-coder:7b-instruct \
  --secondary-proposer-model deepseek-coder:6.7b-instruct \
  --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct \
  --judge-model qwen2.5-s2t-advisor:3b \
  --provider-timeout-sec 120
```

## 3. Current Truth

### Proven from this live run

```text
- delegated_retry_committee_path_used = true
- delegated_retry_committee_candidate_count = 2
- qwen2.5-coder:7b-instruct was actually called and produced candidate output
- deepseek-coder:6.7b-instruct was actually called and produced candidate output
- candidate-specific rejection truth is preserved in delegated_retry_committee_candidates_json
```

### Not proven from this live run

```text
- no committee winner
- solved = false
- verifier_result = fail
- no bounded solve claim allowed
```

## 4. Candidate Truth

Observed candidate-level truth:

```text
Candidate 1:
- model = qwen2.5-coder:7b-instruct
- format_class = UNIFIED_DIFF
- conversion_status = none
- apply_status = format_rejected
- rejection_reason = unified_diff_malformed

Candidate 2:
- model = deepseek-coder:6.7b-instruct
- format_class = EMPTY
- conversion_status = none
- apply_status = empty_patch
- rejection_reason = patch_empty
```

## 5. Main Row Outcome

Latest row truth:

```text
- task_id = toy-math-verifier-evidence-gap
- execution_topology = localheal_pipeline
- local_model_called = true
- verifier_result = fail
- solved = false
- solve_mechanism = delegated_retry_unresolved
- delegated_retry_failure_reason = committee_no_winner
- delegated_retry_committee_path_used = true
- delegated_retry_committee_candidate_count = 2
```

## 6. Important Mismatch Found

The row-level delegated retry summary still says:

```text
delegated_retry_stage = provider_not_called
delegated_retry_provider_called = false
```

But the candidate JSON and live debug output prove:

```text
both committee candidate models were actually invoked
```

Interpretation:

```text
The current row-level delegated retry summary collapses committee candidate
execution into a single-provider field that under-reports real dual-model
candidate calls.
```

## 7. Decision

```text
Dual-model wiring lane: PARTIAL PASS
Solve lane: FAIL
```

Meaning:

```text
The dual-model committee path is now strong enough to prove real heterogeneous
candidate execution on the live Nexus path.

However, the current run does not prove committee solve capability because:
- no candidate passed normalization/apply/verification end to end
- the winner count remained zero
- solve remained false
```
