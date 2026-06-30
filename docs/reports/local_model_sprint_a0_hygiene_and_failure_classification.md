# Local Model Sprint A0: Worktree Hygiene and Failure Classification

**Status:** LOCAL_MODEL_SPRINT_A0_HYGIENE_CLASSIFICATION_COMPLETE
**Date:** 2026-07-01
**Git state:** 15 dirty files

## Git Status

```
?  artifacts/external_sources/sympy_13852
M  artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json
M  artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/action_protocol_001.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_001.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_002.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_004.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_005.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_006.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_007.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/concurrency_008.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/evidence_gap_001.json
M  artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/verifier_gap_001.json
M  nexus/research/domain/__pycache__/__init__.cpython-314.pyc
M  nexus/research/domain/__pycache__/route_planner.cpython-314.pyc
M  nexus/research/domain/__pycache__/routing_receipt.cpython-314.pyc
```

## Ignored Dirty Files

All 15 dirty files are runtime artifacts, pycache, or benchmark outputs:
- `artifacts/external_sources/sympy_13852` — external source cache
- `artifacts/runtime/*` — runtime regression results (10 files)
- `nexus/research/domain/__pycache__/*` — pycache (3 files)

None are staged. None are code files.

## Recent Commits

```
c12b29ec6 docs: plan M1 reuse of existing LocalHeal capabilities
179512191 docs: decide existing parser policy for M1
41c0d0daa test: audit committee to repair seam
1c706ed32 test: verify localheal pipeline seam truth
ab94b708a bench: stabilize M1 wiring telemetry
721f5fea7 docs: audit M1 LocalHeal wiring reuse
9bd3026c1 add M1 real local solve benchmark suite
5a72cde7c enforce CapabilityPlanner downstream authority: align integration stubs with contract
```

## Test Suite Results

**Command:** `uv run pytest -q --maxfail=20` (excluding 4 collection-error files)
**Collected:** 6671 items
**Result:** 1537 passed, 20 failed (maxfail=20), 12 warnings in 202.40s

Note: Full suite did not complete due to timeout (300s). 20 failures hit maxfail before full count.

## Collection Errors (4 files)

| File | Error | Classification |
|------|-------|----------------|
| `tests/gates/test_s2t_memory_sidecar_fixtures.py` | `ModuleNotFoundError: No module named 'jsonschema'` | unrelated_pre_existing |
| `tests/gates/test_s2t_memory_sidecar_schema.py` | `ModuleNotFoundError: No module named 'jsonschema'` | unrelated_pre_existing |
| `tests/integration/test_ollama_local_solve_smoke_runner_contract.py` | `ImportError: cannot import name 'build_local_model_provider_from_env'` | related_to_downstream_enforcement |
| `tests/unit/local_heal/test_qwen_backend_seam.py` | `ImportError: cannot import name 'build_local_model_provider_from_env'` | related_to_downstream_enforcement |

## Failing Tests Classification

### related_to_downstream_enforcement (4 tests)

| Test | Failure | Reason |
|------|---------|--------|
| `test_local_model_adapter_env_enabled_no_model_call_records_blocker` | `assert 'missing_required_control' in ['missing_signal_snapshot']` | Downstream enforcement changed error message from `missing_required_control` to `missing_signal_snapshot` |
| `test_local_model_adapter_june_b_replay` | `assert 'local_only_blocked' == 'cloud_assisted_by_local_trace_only'` | Downstream enforcement changed route_mode when signal_snapshot missing |
| `test_local_model_adapter_wet_run` | `assert 'local_only_blocked' == 'local_only_executed'` | Downstream enforcement blocks execution when signal_snapshot missing |
| `test_local_model_adapter_missing_controls` | `assert 'missing_signal_snapshot' == 'missing_required_control'` | Error message changed by downstream enforcement |

### unrelated_pre_existing (16 tests)

**Architecture boundary (1):**
| Test | Failure |
|------|---------|
| `test_search_context_isolation` | `nexus/search/sampler.py` imports `nexus.verifiers.contracts` |

**Report lock violations (7):**
| Test | Failure |
|------|---------|
| `test_h6_0_audit_report_lock` through `test_h6_6_audit_report_lock` | `h6_13_controlled_provider_probe_denylist_v0.md` contains `production_ready=true` and `public_claim_allowed=true` |

**Hidden verifier / subprocess (8):**
| Test | Failure |
|------|---------|
| `test_hidden_verifier_compact_retry_keeps_candidate_cap` | `assert 0 == 2` — captured_cmds empty, mock not applied |
| `test_hidden_verifier_assertion_uses_deterministic_pre_retry_before_second_model_call` | `FileNotFoundError: .venv/bin/python` — subprocess mock falls through |
| `test_hidden_verifier_retry_can_be_disabled_for_receipt_oracle` | `assert 0 == 1` — captured_cmds empty |
| `test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm` | Command assertion: `.venv/bin/python` vs `uv run` |
| `test_hidden_verifier_overrides_successful_nexus_row` | Assertion on test_hidden.py path |
| `test_hidden_verifier_failure_retries_with_failure_evidence_when_self_heal_env_enabled` | `assert 0 == 2` — captured_cmds empty |
| `test_hidden_verifier_infra_failure_records_skipped_infra_lane` | `KeyError: 'hidden_retry_used'` |
| `test_run_with_nexus_llm_requires_model_and_nexus_evidence` | `FileNotFoundError: .venv/bin/python` |

### related_to_m1_wiring (0 tests)

No M1 wiring failures in current test suite.

### unknown_needs_review (0 tests)

## Explicit Statements

- No code changed in this stage.
- No runtime artifact staged.
- No tests modified.

## Stop Gate Assessment

**4 failures classified as `related_to_downstream_enforcement`.**
These are pre-existing test expectations that were valid before Step 1-4 downstream enforcement was committed. The tests in `tests/benchmark/test_capability_ab_runner.py` expect old adapter behavior (error message `missing_required_control`, route_mode `local_only_executed`). Downstream enforcement changed these to `missing_signal_snapshot` and `local_only_blocked`.

**Stop gate: TRIGGERED.** Do not proceed to Stage A1 without first resolving these 4 adapter test failures, or confirming they are expected behavioral changes from Step 1-4.
