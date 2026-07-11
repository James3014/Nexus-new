# N30R-V1 Runtime Retry Closure

## Root Cause

- **Location**: `nexus/services/local_heal/orchestrator.py`, method `_run_repair_loop`, lines 205-208
- **Behavior**: `_attempt_semantic_retry` correctly patched the file and set `ctx.op.solve_eligible = True` (line 717), but `_run_repair_loop` did NOT check `solve_eligible` after `_handle_verification_failure` returned. The loop continued to attempt patching with WRONG_PATCH on an already-correct file, causing SEARCH mismatch → exhausted retries → empty `final_patch` → `solved=False`.
- **Fix**: Added `if ctx.op.solve_eligible: ctx.gov.gate_exit = "verification"; break` after `_handle_verification_failure(ctx, v_res)` in `_run_repair_loop`.

## Runtime Fix

| File | Change |
|------|--------|
| `orchestrator.py` | Save `_first_attempt_patch_hash` before overwrite; add `solve_eligible` break after `_handle_verification_failure` |
| `local_model_capability_executors.py` | Propagate `first_attempt_patch_hash` in pipeline telemetries |
| `local_model_executor.py` | Forward `first_attempt_patch_hash` to `raw_meta` |
| `n30r_v1_full_armor_trace.py` | Add per-attempt hash tracking + `terminal_status` field |
| `test_n30r_v1_vertical_slice.py` | Update call count (>=4) + telemetry length (>=4); add lifecycle (9) + collapse guard (7) tests |

## Canonical Evidence

- **Run ID**: `1783731744`
- **Artifact directory**: `docs/bench/n30r/v1_artifacts/1783731744/`
- **Trace JSON**: `docs/bench/n30r/v1_full_armor_trace_1783731744.json`

### First Candidate

- hash: `fbafa84a2790602b818d2b8e28f88655c9835c51ac023a43b4125b543063f929`
- apply: `applied`
- verifier: `fail`

### Semantic Retry

- count: `1`
- invocation source: `orchestrator_semantic_retry`
- prompt classification: `SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE`
- prompt contains locked search: `True`
- prompt contains target symbol: `True`

### Second Candidate

- hash: `5890d34aabed18d6de0655740da45c7a788a9a5512f9a8f025767981268853fb`
- differs from first: `True`
- isolated: `True`
- apply: `applied`
- verifier: `pass`

### Final Verifier

- candidate_isolated: `True`
- verifier_result: `pass`
- pipeline_solve_eligible: `True`
- solved: `True`
- terminal_status: `DETERMINISTIC_RETRY_VERIFIED_SOLVE`

## Tests

### Focused

```
.venv/bin/pytest tests/bench/test_n30r_v1_vertical_slice.py -q
83 passed in 3.63s
```

### Full

```
.venv/bin/pytest \
  tests/bench/test_n30r_v1_vertical_slice.py \
  tests/bench/test_n30r_real_core_bridge.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_local_model_capability_executors.py \
  tests/unit/local_heal/test_local_model_armor_receipt_gate.py \
  tests/unit/local_heal/test_decoupled_architecture_tdd.py \
  -q
330 passed in 6.54s
```

## Claim Boundary

| Item | Value |
|------|-------|
| Deterministic retry closed | `true` |
| A1 oracle executed | `false` |
| Live Qwen executed | `false` |
| Effectiveness measured | `false` |
| Production ready | `false` |
