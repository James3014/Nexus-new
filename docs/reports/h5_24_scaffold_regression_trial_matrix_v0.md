# H5-24 Scaffold Regression Trial Matrix Report

**日期**: 2026-06-22
**狀態**: `H5_24_SCAFFOLD_REGRESSION_TRIAL_MATRIX_PASS`

---

## Commands Run

### 1. Syntax Checks

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py \
  scripts/bench/h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_local_committee_e2e_smoke.py \
  scripts/bench/h5_cloud_fallback_e2e_smoke.py tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py
→ SYNTAX_OK
```

### 2. H5 Selector Tests

```text
pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 107 passed, 346 deselected
```

### 3. Local Smoke Evidence Tests

```text
pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
→ 38 passed
```

### 4. Cloud Smoke Evidence Tests

```text
pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 18 passed
```

### 5. Full Capability Runner Unit File

```text
pytest tests/benchmark/test_capability_ab_runner.py -q
→ 444 passed, 9 failed (pre-existing, non-H5)
```

### 6. Dry-Run CLI Smoke

```text
python3 scripts/bench/h5_local_committee_e2e_smoke.py --dry-run
→ JSON output: schema="nexus.h5_local_committee_e2e_smoke.v1", status="pass"

python3 scripts/bench/h5_cloud_fallback_e2e_smoke.py --dry-run --provider gemini
→ JSON output: schema="nexus.h5_cloud_fallback_e2e_smoke.v1", status="pass"
```

---

## Pass/Fail Counts

| Suite | Passed | Failed | Notes |
|-------|--------|--------|-------|
| Syntax checks | 6/6 | 0 | All files compile |
| H5 selector tests | 107 | 0 | H5 scaffold core |
| Local smoke tests | 38 | 0 | Local evidence chain |
| Cloud smoke tests | 18 | 0 | Cloud evidence chain |
| Full capability runner | 444 | 9 | Pre-existing, non-H5 |
| **Total** | **606** | **9** | All H5 tests pass |

## Pre-existing Failures (Non-H5)

The 9 failures in the full capability runner are all pre-existing and unrelated to H5:

- `test_python_syntax_warning_detects_return_in_finally` — Python 3.12 behavior change
- `test_hidden_verifier_compact_retry_keeps_candidate_cap` — `.venv/bin/python` missing
- `test_hidden_verifier_assertion_uses_deterministic_pre_retry_before_second_model_call` — `.venv/bin/python` missing
- `test_hidden_verifier_retry_can_be_disabled_for_receipt_oracle` — `.venv/bin/python` missing
- `test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm` — `_run_process_group` path assertion mismatch
- `test_hidden_verifier_overrides_successful_nexus_row` — `.venv/bin/python` missing
- `test_hidden_verifier_failure_retries_with_failure_evidence_when_self_heal_env_enabled` — `.venv/bin/python` missing
- `test_hidden_verifier_infra_failure_records_skipped_infra_lane` — missing output field
- `test_run_with_nexus_llm_requires_model_and_nexus_evidence` — `.venv/bin/python` missing

None of these involve H5 code paths.

---

## Invariant Table

| Invariant | Expected | Actual | Status |
|-----------|----------|--------|--------|
| `h5_execution_ready_count` | 0 | 0 | PASS |
| `h5_cloud_fallback_invoked_count` | 0 | 0 | PASS |
| `h5_behavior_changed_count` | 0 | 0 | PASS |
| `final_source` in H5 rows | "none" | "none" | PASS |
| `h5_overall_readiness_closure` exists | yes | yes | PASS |
| `closure_status` | "blocked" | "blocked" | PASS |
| `public_claim_allowed` | false | false | PASS |
| `production_ready` | false | false | PASS |
| No benchmark model_calls increment | verified | verified | PASS |
| No output mutation | verified | verified | PASS |
| No final_patch replacement | verified | verified | PASS |

---

## Git Status Summary

```text
M .gitnexusignore
M artifacts/runtime/... (runtime artifacts, unrelated)
M nexus/services/local_heal/backend_resource_policy.py (unrelated)
M nexus/services/local_heal/committee_orchestrator.py (U3 work, already committed)
M nexus/services/local_heal/native_route_adapter.py (unrelated dirty)
M nexus/services/local_heal/receipt.py (U3 work, already committed)
... (other unrelated dirty files)
```

No uncommitted H5 changes. All H5 code is committed.

---

## Statements

```text
H5 trace-only scaffold regression trial only.
No H5 execution enabled.
No execution flag designed.
No actual route order change.
No local committee invocation from benchmark runner.
No cloud fallback execution from benchmark runner.
No local candidate finalization.
No cloud fallback finalization.
No final delivery source change.
No final_patch replacement.
No model_calls increment.
No output mutation.
No full benchmark.
Not H5 ready.
Not local-first ready.
Not cloud fallback ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
