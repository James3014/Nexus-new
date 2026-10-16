# June-B Real ABC Replay Report (P12)

**Created Date**: 2026-06-29  
**Status**: COMPLETE  

This report evaluates the execution of the 5 June-B baseline tasks under real local model settings and details the telemetry collected in the evidence bundle.

## 1. Verdict

**Verdict**: `FAIL_REPLAY_BLOCKED`  
**Reason**: All active tasks in the baseline set (`full_rerun_task_set.json`) lack the necessary control parameters (`target_file`, `locked_search`, `target_symbol`, `evidence_refs`) required to trigger real local candidate generation and isolated workspace application. Consequently, they are safely blocked at the adapter boundary, and `local_model_called_count` remains `0`.

## 2. Baseline Comparison

- **June-B Standalone Baseline**: Tasks failed due to `INFRA_BLOCKED` or `MOCK_ORACLE_REPLAY_FAIL`.
- **P10a Mocked ABC Replay**: Simulated using mock `urlopen` responses to return patches, showing dummy workspace success metrics.
- **P12 Real ABC Replay**: Successfully executed the real runner finalization pipeline against the real taskset. Ensured 100% fail-closed routing at the adapter boundary due to missing controls.

## 3. Evidence Summary

The following is the `local_model_adapter_summary` collected in `evidence_bundle.json`:

```json
{
  "adapter_trace_count": 5,
  "adapter_invoked_count": 0,
  "local_model_called_count": 0,
  "candidate_isolated_count": 0,
  "hash_match_count": 0,
  "verifier_pass_count": 0,
  "fail_closed_count": 5,
  "behavior_changed_count": 0,
  "public_claim_allowed_count": 0,
  "production_ready_count": 0,
  "adapter_error_count": 0,
  "adapter_missing_control_count": 5,
  "adapter_contract_violation_count": 0,
  "adapter_dry_run_count": 0,
  "adapter_blocked_count": 5
}
```

## 4. Safety Locks

All safety locks evaluated to `0`, ensuring that the fail-closed boundaries were strictly maintained:

- `public_claim_allowed_count`: **0**
- `production_ready_count`: **0**
- `behavior_changed_count`: **0**
- `adapter_contract_violation_count`: **0**
- `adapter_error_count`: **0**
- `adapter_missing_control_count`: **5**

## 5. Provider & Model Parameters

- `NEXUS_LOCAL_MODEL_PROVIDER`: `ollama`
- `NEXUS_LOCAL_MODEL_NAME`: `qwen2.5-coder:14b-instruct-q3_K_M` (Locally available model)
- Did the system call the local model during replay? **No**, because missing controls prevented model invocation.
- `local_model_called_count`: **0**

## 6. Replay Limitations

- **Missing Workspaces**: None (astropy and sympy directories were present).
- **Missing Controls**: 4 active tasks (`astropy-13236`, `sympy-13852`, `astropy-12907`, `astropy-14182`) completely lack `target_file`, `locked_search`, and `target_symbol` in the baseline metadata.
- **Provider / Verifier Unavailable**: None.
- **Tasks Excluded**: 1 task (`sympy-11618`) is marked as `BASELINE_ONLY` (boundary shadow task).

## 7. Git Hygiene

### Git Status Before P12 Replay:
```text
? artifacts/external_sources/sympy_13852
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json
M artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl
```

### Git Status After P12 Replay:
```text
? artifacts/external_sources/sympy_13852
? artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/
? docs/reports/local_model_armor_p12_artifact_hygiene_seal.md
? docs/reports/local_model_armor_p12_june_b_baseline_inventory.md
? docs/reports/local_model_armor_p12_real_june_b_replay.md
? scripts/bench/run_p12_real_replay.py
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json
M artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl
```

### Intentionally Created/Modified (Whitelisted):
- `docs/reports/local_model_armor_p12_artifact_hygiene_seal.md`
- `docs/reports/local_model_armor_p12_june_b_baseline_inventory.md`
- `docs/reports/local_model_armor_p12_real_june_b_replay.md`
- `artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/replay_manifest.json`
- `artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/evidence_bundle.json`
- `scripts/bench/run_p12_real_replay.py`
- `tests/benchmark/test_p12_replay.py`

### Explicitly Excluded (Blacklisted):
- `artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl`
- `artifacts/external_sources/sympy_13852`
- `artifacts/runtime/ao2_live_regression_entrypoints_v0/*`
- `artifacts/runtime/av_executable_benchmark_substrate_v0/*`
- Docker/F-07B files
