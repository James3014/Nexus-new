# Task Card: mimo-workforce-policy-writeback-20260817

artifact_authority: current
task_id: `mimo-workforce-policy-writeback-20260817`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Persist the Owner-approved 2026-08-17 OpenCode MiMo V2.5 cumulative calibration and governance evidence into the existing canonical Nexus workforce authority/evidence files while preserving the frozen 2026-07-29 raw benchmark and keeping admitted MiMo autonomy at L1. Record semantic stable floor L1.5, semantic frontier L3, 51/53 semantic score across 53 new non-baseline trials, frontier stress 15/15, verifier-guided repair 4/5, strict-schema conditionality, verified tool/scope-discipline hard failure, Free-first paid-Go pre-mutation fallback policy, unresolved Free/Go semantic-lineage equivalence, and the dedicated DevSpace tool-discipline requalification follow-on gate. Do not admit opencode-go/mimo-v2.5, do not promote MiMo autonomy, and do not create parallel policy/report files.

## Allowed files

- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `docs/reports/model_workforce_three_arm_calibration_20260729.md`
- `nexus/config/model_workforce.yaml`
- `tests/contracts/test_model_workforce_policy.py`

## Verification commands

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
