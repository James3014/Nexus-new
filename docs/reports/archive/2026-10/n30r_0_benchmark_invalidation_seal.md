# N30R-0 Closeout: Benchmark Invalidation Seal

**Status**: N30R_0_BENCHMARK_INVALIDATION_SEALED

## baseline commit SHA
`88f9e50fd66aaaefe3002788496b74f76f809588`

## Historical artifacts inspected
- `docs/bench/n28_4quadrants_results.json` — N28 48-run results
- `docs/bench/n30a_4quadrants_results.json` — N30A 48-run results
- `docs/reports/n28-closeout.md` — N28 closeout report
- `docs/bench/n29_4quadrants_lite_results.json` — N29 Lite results

## N28 invalidation reasons
- `task_bank_original_verifier_passes`: original source passes verifier on 11/12 tasks
- `bare_arm_not_bare`: bare quadrant still calls LocalHealCapabilityAdapter
- `quadrant_execution_not_isolated`: quadrants do not change execution behavior

## N30A invalidation reasons
- `task_bank_original_verifier_passes`: same taskset as N28
- `quadrant_execution_paths_identical`: quadrants do not change execution behavior
- `model_call_evidence_incomplete`: 48 failed rows with total duration ~13s
- `empty_or_timeout_output_not_fail_closed`: smoke only asserts model labels

## M5 paired-baseline limitation
- `source_prompt_verifier_hashes_incomplete`: lacks enough hashes for strict paired baseline

## Files changed
- `docs/bench/n30r_baseline_manifest.json` (created)
- `tests/bench/test_n30r_baseline_manifest.py` (created)

## Exact commands run
```bash
python3 -m json.tool docs/bench/n30r_baseline_manifest.json >/dev/null
python3 -m py_compile tests/bench/test_n30r_baseline_manifest.py
pytest tests/bench/test_n30r_baseline_manifest.py -v
git diff --check
```

## Test count
6 passed

## Statements
- No historical artifact modified
- No model calls
- N30-B/C/D remain paused
- production_ready=false
- public_claim_allowed=false
