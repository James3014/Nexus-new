# Test Evidence

## Command 1: Compile check
```bash
python3 -m py_compile nexus/services/local_heal/local_model_executor.py nexus/services/local_heal/local_model_capability_executors.py scripts/bench/capability_ab_runner.py
```
- **Exit code**: 0
- **Result**: PASS (all modules compile)

## Command 2: Planner path tests
```bash
python3 -m pytest tests/benchmark/test_local_model_executor_planner_path.py -q
```
- **Exit code**: 0
- **Result**: 3 passed, 2 skipped
- **Skipped tests**:
  - `test_local_model_executor_real_provider_smoke` — skipped (requires real Ollama provider)
  - `test_local_model_executor_concurrency_real_solve` — skipped (requires real Ollama provider)

## Command 3: Pipeline seam truth tests
```bash
python3 -m pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py -q
```
- **Exit code**: 1
- **Result**: 7 passed, 30 failed
- **Failure reason**: Missing `rank_bm25` module (`ModuleNotFoundError: No module named 'rank_bm25'`)
- **First failure traceback**:
```
tests/unit/local_heal/test_localheal_pipeline_seam_truth.py:864: in test_pipeline_result_non_empty_final_patch_projects_candidate_hash
    from nexus.services.local_heal.pipeline import HealPipeline
nexus/services/local_heal/pipeline.py:20: in <module>
    from nexus.services.local_heal.phases.localization import LocalizationPhase
nexus/services/local_heal/granular_localizer.py:6: in <module>
    from rank_bm25 import BM25Okapi
E   ModuleNotFoundError: No module named 'rank_bm25'
```

## Command 4: Armor receipt gate tests
```bash
python3 -m pytest tests/unit/local_heal/test_local_model_armor_receipt_gate.py -q
```
- **Exit code**: 0
- **Result**: 19 passed

## Command 5: Committee runtime activation tests
```bash
python3 -m pytest tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py -q
```
- **Exit code**: 0
- **Result**: 11 passed

## Command 6: Executor topology tests
```bash
python3 -m pytest tests/unit/local_heal/test_local_model_executor.py -k "localheal_pipeline or local_committee_only or planner or topology or armor" -q
```
- **Exit code**: 1
- **Result**: 28 passed, 1 failed, 145 deselected
- **Failure reason**: Missing `rank_bm25` module
- **First failure traceback**:
```
tests/unit/local_heal/test_local_model_executor.py::test_localheal_pipeline_verifier_fail_delegates_existing_retry_with_seeded_evidence
    from nexus.services.local_heal.pipeline import HealPipeline
nexus.services.local_heal/pipeline.py:20: in <module>
    from nexus.services.local_heal.phases.localization import LocalizationPhase
nexus.services.local_heal/granular_localizer.py:6: in <module>
    from rank_bm25 import BM25Okapi
E   ModuleNotFoundError: No module named 'rank_bm25'
```

## Summary
| Command | Passed | Failed | Skipped | Blocked by |
|---------|--------|--------|---------|------------|
| Compile check | - | 0 | - | - |
| Planner path | 3 | 0 | 2 | Real Ollama env |
| Pipeline seam | 7 | 30 | 0 | rank_bm25 module |
| Armor receipt gate | 19 | 0 | 0 | - |
| Committee activation | 11 | 0 | 0 | - |
| Executor topology | 28 | 1 | 0 | rank_bm25 module |
