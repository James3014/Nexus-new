# N30R-2 Closeout: Four-Task Smoke Bank

**Status**: N30R_2_SMOKE_TASK_BANK_PASS

## Four task IDs
- n30r_smoke_syntax (SyntaxError — missing colon)
- n30r_smoke_anchor (NameError — wrong variable)
- n30r_smoke_semantic (AssertionError — wrong return value)
- n30r_smoke_multi (AssertionError — wrong increment)

## 3× original FAIL evidence
All 4 tasks: 3/3 deterministic FAIL on original source.

## 3× golden PASS evidence
All 4 tasks: 3/3 deterministic PASS on golden source.

## Task hashes
Each task has stable source, verifier, environment, and task bundle SHA256.

## No-overlap policy
Smoke task IDs do not overlap with any future heldout task IDs.

## Golden leakage check
No golden patch body in smoke_manifest.json.

## Files changed
- docs/bench/n30r/smoke_manifest.json (created)
- scripts/bench/n30r_task_gate.py (created)
- tests/bench/test_n30r_smoke_task_bank.py (created)
- tests/fixtures/n30r/smoke/ (4 fixture files)

## Exact commands
```bash
python3 -m py_compile scripts/bench/n30r_task_gate.py tests/bench/test_n30r_smoke_task_bank.py
pytest tests/bench/test_n30r_smoke_task_bank.py -v
python3 scripts/bench/n30r_task_gate.py --manifest docs/bench/n30r/smoke_manifest.json --repetitions 3 --output /tmp/n30r_smoke_gate_receipts.json
```

## Test count
13 passed

## Statements
- No model calls
- Smoke tasks are not heldout tasks
- production_ready=false
- public_claim_allowed=false
