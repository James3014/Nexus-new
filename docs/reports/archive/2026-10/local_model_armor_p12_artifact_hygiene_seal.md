# Artifact Hygiene Seal (P12)

**Created Date**: 2026-06-29  
**Status**: ACTIVE & SEALED  

This document records the baseline of pre-existing untracked/dirty files in the workspace to prevent leakage into the P12 ABC Replay commits.

## 1. Git Status (Before Execution)

```text
? artifacts/external_sources/sympy_13852
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json
M artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/action_protocol_001.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_001.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_002.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_004.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_005.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_006.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_007.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_008.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/evidence_gap_001.json
M artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/verifier_gap_001.json
M artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl
```

## 2. Dirty File Classification

- **pre_existing_runtime_dirty**:
  - `artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json`
  - `artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json`
  - `artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json`
  - `artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl`
- **pre_existing_external_source_dirty**:
  - `artifacts/external_sources/sympy_13852`
- **task_generated_candidate**:
  - None
- **safe_to_ignore**:
  - None
- **must_not_commit**:
  - All files listed in `pre_existing_runtime_dirty` and `pre_existing_external_source_dirty`.

## 3. Policy & Exclusions

- **Allowed Read Paths**:
  - `artifacts/runtime/real_qwen_small_batch_eval_v0/full_rerun_task_set.json`
  - `artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl`
- **Forbidden Actions**:
  - **DO NOT** edit or modify `artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl`.
  - **DO NOT** commit any files in the blacklist.
  - **DO NOT** perform destructive clean/stash on pre-existing files without authorization.
- **Dedicated Target Directory for P12**:
  - All outputs from P12 ABC Replay must be placed in `artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/`.

## 4. Commit Rules

- **Whitelist (Allowed to Commit)**:
  - `docs/reports/local_model_armor_p12_artifact_hygiene_seal.md`
  - `docs/reports/local_model_armor_p12_june_b_baseline_inventory.md`
  - `docs/reports/local_model_armor_p12_real_june_b_replay.md`
  - `artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/replay_manifest.json`
  - `artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/evidence_bundle.json`
  - `scripts/bench/run_p12_real_replay.py`
  - `tests/benchmark/test_p12_replay.py`
- **Blacklist (Forbidden to Commit)**:
  - `artifacts/runtime/real_qwen_small_batch_eval_v0/results.jsonl`
  - `artifacts/external_sources/sympy_13852`
  - `artifacts/runtime/ao2_live_regression_entrypoints_v0/*`
  - `artifacts/runtime/av_executable_benchmark_substrate_v0/*`
