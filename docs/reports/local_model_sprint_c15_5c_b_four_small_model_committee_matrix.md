# LocalHeal Sprint C15-5C-B: Four Small-Model Committee Matrix

**Status**: `C15_5C_B_FOUR_SMALL_MODEL_MATRIX_ALL_FAILED`

---

## 1. Git State and HEAD Verification
```text
=== git status --short ===
M .nexus/reports/learn/learning_closure.jsonl
 M .serena/project.yml
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
 M docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md
 M nexus/experimental/__pycache__/__init__.cpython-314.pyc
 M nexus/experimental/__pycache__/sandboxed_adapter.cpython-314.pyc
 M nexus/research/domain/__pycache__/__init__.cpython-314.pyc
 M nexus/research/domain/__pycache__/route_planner.cpython-314.pyc
 M nexus/research/domain/__pycache__/routing_receipt.cpython-314.pyc
 M nexus/rollout/__pycache__/__init__.cpython-314.pyc
 M nexus/rollout/__pycache__/canary_guard.cpython-314.pyc
 M nexus/services/local_heal/prompt_builder.py
 M nexus/verifiers/domain/astropy/__pycache__/__init__.cpython-314.pyc
 M nexus/verifiers/domain/astropy/__pycache__/astrophysics_guard.cpython-314.pyc
 M nexus/verifiers/domain/astropy/__pycache__/fits_reader.cpython-314.pyc
 M nexus/verifiers/domain/common_core/__pycache__/__init__.cpython-314.pyc
 M nexus/verifiers/domain/common_core/__pycache__/lock_helpers.cpython-314.pyc
 M nexus/verifiers/domain/common_core/__pycache__/state_guards.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/__init__.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/buggy_targets.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b01.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b02.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/fixed_targets.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b01.cpython-314.pyc
 M nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b02.cpython-314.pyc
 M nexus/verifiers/domain/django/__pycache__/__init__.cpython-314.pyc
 M nexus/verifiers/domain/django/__pycache__/django_core_logic_guard.cpython-314.pyc
 M nexus/verifiers/domain/django/__pycache__/django_migration_guard.cpython-314.pyc
 M tests/unit/experimental/__pycache__/__init__.cpython-314.pyc
 M tests/unit/local_heal/test_local_model_executor.py
 M tests/unit/research/__pycache__/__init__.cpython-314.pyc
 M tests/unit/rollout/__pycache__/__init__.cpython-314.pyc
 M tests/unit/verifiers/astropy/__pycache__/__init__.cpython-314.pyc
 M tests/unit/verifiers/common_core/__pycache__/__init__.cpython-314.pyc
 M tests/unit/verifiers/concurrency/__pycache__/__init__.cpython-314.pyc
 M tests/unit/verifiers/django/__pycache__/__init__.cpython-314.pyc
?? codebase-memory-mcp
?? docs/reports/local_model_sprint_c15_3f_bounded_live_validation_after_verifier_receipt_fix.md
?? docs/research/nexus-knowledge-agent-integration.md
?? scratch/diagnose_reanchor.py
?? scratch/parse_to_md.py
?? scratch/run_all_matrix.py
?? scratch/smoke_test_models.py
?? scratch/smoke_test_ornith.py
?? scratch/smoke_test_ornith_v3.py

=== git log -3 --oneline ===
8039317d3 test(localheal): complete four small-model committee matrix
63a31ee32 fix(localheal): C15-5C implement four small-model committee test flows and telemetry verification
970d10744 fix(localheal): honor executor model in delegated retry

=== git show --stat --oneline --no-renames HEAD ===
8039317d3 test(localheal): complete four small-model committee matrix
 Modelfile.qwythos                                  |  19 +++
 ...t_c15_5c_b_four_small_model_committee_matrix.md | 137 +++++++++++++++++++++
 nexus/services/local_heal/local_model_executor.py  |   2 +-
 3 files changed, 157 insertions(+), 1 deletion(-)
```

---

## 2. Ollama Model List
```text
NAME                                 ID              SIZE      MODIFIED    
qwythos:9b                           1d9d9a0c78bc    5.6 GB    2 hours ago    
ornith:9b                            a75697c14589    5.6 GB    3 hours ago    
qwen2.5-coder:7b-instruct            3c6217f476a7    4.7 GB    4 days ago     
deepseek-coder:6.7b-instruct         ce298d984115    3.8 GB    4 days ago     
qwen2.5-coder:14b-instruct-q3_K_M    e00d09afd55a    7.3 GB    13 days ago    
deepseek-r1-14b-q4km:latest          2499dfb9e4e2    9.0 GB    2 weeks ago    
gemma4-coder-12b-q4km:latest         c0d776a20fb6    7.4 GB    2 weeks ago    
qwen2.5:1.5b                         65ec06548149    986 MB    2 weeks ago    
qwen2.5-s2t-advisor:3b               357c53fb659c    1.9 GB    2 weeks ago    
nomic-embed-text:latest              0a109f422b47    274 MB    5 weeks ago
```

---

## 3. New Model Smoke Test

### ornith:9b Smoke Test
* **Command**: `python3 scratch/smoke_test_models.py`
* **Model Invoked**: `ornith:9b`
* **Wall Time**: `24.78s`
* **Output Length**: `331`
* **SEARCH/REPLACE present**: `True`
* **Prose Contamination**: `False`
* **Timeout**: `False`
* **Load Failed**: `False`
* **Response Excerpt**: `SEARCH/REPLACE: toy/math_util.py\n<<<<<<< SEARCH\ndef normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)\n=======\ndef ...`

### qwythos:9b Smoke Test
* **Command**: `python3 scratch/smoke_test_models.py`
* **Model Invoked**: `qwythos:9b`
* **Wall Time**: `64.65s`
* **Output Length**: `2902`
* **SEARCH/REPLACE present**: `True`
* **Prose Contamination**: `True` (contained introductory/conversational filler in the prompt wrapper)
* **Timeout**: `False`
* **Load Failed**: `False`
* **Response Excerpt**: `The user wants me to act as a coding assistant and only output SEARCH/REPLACE blocks without any conversational filler or prose. I need to carefully review...`

---

## 4. C15-5C-B Benchmark Commands
```bash
# Outer timeout: 900s, Provider timeout: 240s
# Commands executed sequentially:
python3 scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --delegated-retry-candidate-models "ornith:9b,qwythos:9b" --provider-timeout-sec 240
```

---

## 5. 2-Model Committee Matrix

| ID | Combination | Status | Duration | Candidate Count | Selected Model | Overall Verifier | Solved | Dominant Failure |
|---|---|---|---|---|---|---|---|---|
| A1 | qwen2.5-coder + deepseek-coder | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| A2 | qwen2.5-coder + ornith | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| A3 | qwen2.5-coder + qwythos | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| A4 | deepseek-coder + ornith | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| A5 | deepseek-coder + qwythos | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| A6 | ornith + qwythos | FAIL | 402.21s | 2 | None | fail | false | LOGIC_REGRESSION:VERIFICATION_FAILED |

---

## 6. 3-Model Committee Matrix

| ID | Combination | Status | Duration | Candidate Count | Selected Model | Overall Verifier | Solved | Dominant Failure |
|---|---|---|---|---|---|---|---|---|
| B1 | qwen2.5-coder + deepseek-coder + ornith | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| B2 | qwen2.5-coder + deepseek-coder + qwythos | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| B3 | qwen2.5-coder + ornith + qwythos | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |
| B4 | deepseek-coder + ornith + qwythos | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |

---

## 7. Candidate Receipt Summary

| Combo | Candidate Model | Provider Invoked | Excerpt Len | Apply Status | Candidate Hash | Isolated Verifier | Selected | Rejection Reason |
|---|---|---|---|---|---|---|---|---|
| ornith+qwythos | ornith:9b | True | 300 | failed | a53978037d80 | fail | false | apply_failed: failed |
| ornith+qwythos | qwythos:9b | True | 0 | empty_patch | N/A | fail | false | patch_empty |

---

## 8. Nexus Capability Usage Checklist

* **delegated_retry_committee_path_used**: True
* **run_isolated_workspace_apply_called**: True (for non-empty candidates)
* **run_isolated_verifier_called**: True (for applied candidates)
* **selected_candidate_hash_matches_applied**: False (no candidate passed overall verifier)
* **candidate_isolated**: True (candidates applied to isolated workspaces)
* **verifier_result**: fail
* **solved**: false

---

## 9. Solved Criteria Checklist

* **Selected candidate verifier_result = pass?** ❌ No
* **selected_candidate_hash_matches_applied = true?** ❌ No
* **Overall solved = true?** ❌ No

