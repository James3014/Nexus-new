# N30R-3 Closeout: Two-Arm Runner Contract

**Status**: N30R_3_TWO_ARM_RUNNER_CONTRACT_PASS

## Runner architecture
- Materialize tasks from manifest
- Arm adapters for bare and core
- Fresh workspace per task × trial × arm
- Deterministic verifier as final authority
- JSONL receipt writer

## Bare-arm boundary
- No CapabilityPlanner
- No LocalModelExecutor
- No assertion rewriting, anchor shaping, semantic retry, committee, memory, CodeIntel

## Core-arm boundary
- Uses assertion-grounded problem statement
- Uses planner-owned signal snapshot (arm_config_sha256 differs from bare)
- Same 7B model as bare

## Planner authority evidence
- Core arm arm_config_sha256 ≠ bare arm arm_config_sha256
- Core arm nexus_enabled=True, core_armor_enabled=True

## Workspace isolation evidence
- Each task × trial × arm gets fresh workspace
- Paired arms use identical source/verifier/environment hashes

## Terminal status behavior
- Empty output → INFRA_INVALID (not VERIFIED_FAIL)
- Model timeout → MODEL_TIMEOUT (not INFRA_INVALID)
- Provider mismatch → trust_mismatch=true

## Golden leakage prevention
- Golden patch not in prompt
- Only SHA256 in public receipt

## Files changed
- scripts/bench/n30r_arm_adapters.py (created)
- scripts/bench/n30r_runner.py (created)
- tests/bench/test_n30r_runner_contract.py (created)

## Exact commands
```bash
python3 -m py_compile scripts/bench/n30r_arm_adapters.py scripts/bench/n30r_runner.py tests/bench/test_n30r_runner_contract.py
pytest tests/bench/test_n30r_contracts.py tests/bench/test_n30r_smoke_task_bank.py tests/bench/test_n30r_runner_contract.py -v
python3 scripts/bench/n30r_runner.py --manifest docs/bench/n30r/smoke_manifest.json --arms N30R_A_7B_BARE,N30R_B_7B_CORE --trials 1 --seed 3001 --output /tmp/n30r_dry_run.jsonl --dry-run
git diff --check
```

## Test count
18 passed (runner contract) + 13 (contracts) + 13 (smoke bank) = 44 total

## Statements
- provider calls during tests: 0
- live model calls: 0
- production_ready=false
- public_claim_allowed=false
