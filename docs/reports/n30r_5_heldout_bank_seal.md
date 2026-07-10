# N30R-5 Closeout: 24-Task Heldout Bank and Seal

**Status**: N30R_5_HELDOUT_BANK_SEALED

## 24 task IDs
h_loc_01-06, h_syn_01-06, h_sem_01-06, h_mix_01-06

## Failure-family distribution
- localization: 6
- syntax: 6
- semantic: 6
- mixed: 6

## 3× original-fail evidence
All 24 tasks: 3/3 deterministic FAIL

## 3× golden-pass evidence
All 24 tasks: 3/3 deterministic PASS

## Overlap count
0 (heldout disjoint from smoke)

## Leakage count
0

## Manifest hash
9896a915e98317ed...

## Seal hash
In docs/bench/n30r/heldout_seal.json

## Exact commands
```bash
python3 -m py_compile tests/bench/test_n30r_heldout_task_bank.py
pytest tests/bench/test_n30r_heldout_task_bank.py -v
python3 scripts/bench/n30r_task_gate.py --manifest docs/bench/n30r/heldout_manifest.json --repetitions 3 --output /tmp/n30r_heldout_gate_receipts.json
```

## Tests
12 passed

## Files changed
- docs/bench/n30r/heldout_manifest.json (created)
- docs/bench/n30r/heldout_seal.json (created)
- tests/bench/test_n30r_heldout_task_bank.py (created)
- tests/fixtures/n30r/heldout/ (25 files: heldout_tasks.py + 24 fixtures)

## Statements
- No model calls
- No model-informed task tuning
- production_ready=false
- public_claim_allowed=false
