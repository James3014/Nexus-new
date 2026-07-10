# N30R-1 Closeout: Canonical Benchmark Contract

**Status**: N30R_1_CANONICAL_CONTRACT_PASS

## Terminal statuses
VERIFIED_SOLVE, VERIFIED_FAIL, MODEL_TIMEOUT, INFRA_INVALID, CONTRACT_INVALID, LEAKAGE_INVALID

## Task schema
N30RTaskSpec: 14 fields including split, source SHA256, golden patch SHA256 (body private)

## Arm schema
N30RArmSpec: 8 fields including arm_config_sha256

## Attempt receipt schema
N30RAttemptReceipt: 33 fields with validate_terminal_invariants()

## Timeout classification
- timed_out=true + MODEL_TIMEOUT: valid
- timed_out=true + not MODEL_TIMEOUT: invariant violation
- INFRA_INVALID must not be used for model timeout

## Leakage policy
- golden_patch_body forbidden in public manifest
- only SHA256 + private_ref allowed
- LEAKAGE_INVALID terminal status

## Paired hash invariants
- task_bundle, source, verifier, environment: must match across arms
- rendered_prompt: may differ across arms
- arm_config: must differ

## Files changed
- scripts/bench/n30r_contracts.py (created)
- tests/bench/test_n30r_contracts.py (created)

## Exact commands
```bash
python3 -m py_compile scripts/bench/n30r_contracts.py tests/bench/test_n30r_contracts.py
pytest tests/bench/test_n30r_contracts.py -v
git diff --check
```

## Test count
13 passed

## Statements
- No model calls
- No task fixtures created
- production_ready=false
- public_claim_allowed=false
