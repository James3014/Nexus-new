# H6-1: Shadow Local Adapter Dry Run

**Status**: H6_1_SHADOW_LOCAL_ADAPTER_DRY_RUN_PASS

## Summary

H6-1 validates the shadow local adapter dry-run receipt. This phase simulates the adapter invocation path and produces structured receipts proving that a local adapter can be routed, validated, and blocked from side effects. H6-1 does not call real Qwen models, does not invoke Ollama, and does not perform real inference.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 34 H6-1 tests (T01-T36)
- `scripts/bench/capability_ab_runner.py` — Added `_build_h6_shadow_local_adapter_dry_run` helper function
- `docs/reports/h6_1_shadow_local_adapter_dry_run_v0.md` — This report

## Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_1" --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_1" -q
NEXUS_H6_ALLOW_SHADOW_LOCAL_ADAPTER_DRY_RUN=1 python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_1" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_0 or h6_1" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

- H6-1 collect-only: 34 selected
- H6-1 targeted default env: 34 passed
- H6-1 flagged env: 34 passed
- H6-0/H6-1 targeted: 64 passed
- H5/H6 selector suite: 541 passed
- Local smoke: 38 passed
- Cloud smoke: 18 passed

## Shadow Dry-Run Schema

The schema is `nexus.hybrid_h6_shadow_local_adapter_dry_run.v1`. All outputs include:
- `evaluated: true`
- `dry_run_status: shadow_local_adapter_dry_run_ready | shadow_local_adapter_dry_run_fail | blocked`
- `production_ready: false`
- `public_claim_allowed: false`

## Valid Request/Receipt Examples

### Qwen 3B Selector

**Request**:
```json
{
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run",
  "request_id": "shadow-req-001"
}
```

**Receipt**:
```json
{
  "request_id": "shadow-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "receipt_status": "dry_run_only",
  "runtime_effect": false
}
```

### Qwen 7B Localizer

**Request**:
```json
{
  "adapter_id": "qwen7b-localizer-v0",
  "model_family": "qwen",
  "model_size": "7b",
  "model_name": "qwen2.5-coder:7b",
  "role": "localizer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run",
  "request_id": "shadow-req-002"
}
```

**Receipt**:
```json
{
  "request_id": "shadow-req-002",
  "adapter_id": "qwen7b-localizer-v0",
  "receipt_status": "dry_run_only",
  "runtime_effect": false
}
```

### Qwen 14B Patch Synthesizer

**Request**:
```json
{
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "model_family": "qwen",
  "model_size": "14b",
  "model_name": "qwen2.5-coder:14b",
  "role": "patch_synthesizer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run",
  "request_id": "shadow-req-003"
}
```

**Receipt**:
```json
{
  "request_id": "shadow-req-003",
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "receipt_status": "dry_run_only",
  "runtime_effect": false
}
```

### Verifier Assist

**Request**:
```json
{
  "adapter_id": "qwen3b-verifier-assist-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "verifier_assist",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run",
  "request_id": "shadow-req-004"
}
```

**Receipt**:
```json
{
  "request_id": "shadow-req-004",
  "adapter_id": "qwen3b-verifier-assist-v0",
  "receipt_status": "dry_run_only",
  "runtime_effect": false
}
```

## Invalid Request Examples

### Missing Adapter ID

```json
{
  "adapter_id": "",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run"
}
```
**Result**: `missing_adapter_id` reason, request invalid

### Missing Model Name

```json
{
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run"
}
```
**Result**: `missing_model_name` reason, request invalid

### Invalid Role

```json
{
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "proposer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run"
}
```
**Result**: `missing_role` reason, request invalid

### Invalid Route Mode

```json
{
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "cloud_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "dry_run"
}
```
**Result**: `missing_route_mode` reason, request invalid

### Invalid Shadow Mode

```json
{
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "shadow_mode": "production"
}
```
**Result**: `invalid_shadow_mode` reason, request invalid

## Invalid Receipt Examples

### Invalid Receipt Status

```json
{
  "request_id": "shadow-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "receipt_status": "production",
  "runtime_effect": false
}
```
**Result**: `invalid_receipt` reason, receipt invalid

### Runtime Effect True

```json
{
  "request_id": "shadow-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "receipt_status": "dry_run_only",
  "runtime_effect": true
}
```
**Result**: `runtime_effect_detected` reason, receipt invalid, safety_violation_count=1

## Side-Effect Blocker Examples

### Model Call Executed

```json
{
  "model_call_executed": true,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false
}
```
**Result**: `model_call_executed_detected` reason, safety_violation_count=1

### Ollama Invoked

```json
{
  "model_call_executed": false,
  "ollama_invoked": true,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false
}
```
**Result**: `ollama_invoked_detected` reason, safety_violation_count=1

### Cloud Invoked

```json
{
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": true,
  "repo_mutated": false,
  "behavior_changed": false
}
```
**Result**: `cloud_invoked_detected` reason, safety_violation_count=1

### Repo Mutated

```json
{
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": true,
  "behavior_changed": false
}
```
**Result**: `repo_mutated_detected` reason, safety_violation_count=1

### Behavior Changed

```json
{
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": true
}
```
**Result**: `behavior_changed_detected` reason, safety_violation_count=1

## Proof: No Model Calls Executed

- All valid requests have `model_call_executed: false`
- Test T23 verifies detection of `model_call_executed: true` triggers failure
- Audit scan confirms no test functions execute real model calls

## Proof: No Ollama Invocation

- All valid requests have `ollama_invoked: false`
- Test T24 verifies detection of `ollama_invoked: true` triggers failure
- `ollama_invocation_blocked` is a permanent reason in dry-run output

## Proof: No Cloud Invocation

- All valid requests have `cloud_invoked: false`
- Test T25 verifies detection of `cloud_invoked: true` triggers failure
- `cloud_invocation_blocked` is a permanent reason in dry-run output

## Proof: No Repo Mutation

- All valid requests have `repo_mutated: false`
- Test T26 verifies detection of `repo_mutated: true` triggers failure
- `repo_mutation_blocked` is a permanent reason in dry-run output

## Proof: No Runtime Effect

- All valid receipts have `runtime_effect: false`
- Test T22 verifies detection of `runtime_effect: true` triggers failure
- `runtime_effect_blocked` is a permanent reason in dry-run output

## Proof: ready_for_h6_2_adapter_io_schema_test Can Become True

- Tests T12-T15 demonstrate: when all conditions met, `ready_for_h6_2_adapter_io_schema_test` is True
- Condition: adapter_dry_run_receipt_ready AND safety_violation_count == 0

## Proof: No Duplicate H5/H6 Tests

```
duplicate_h5_h6_tests []
```

Audit scan confirmed: no duplicate test function names across H5 and H6 test suites.

## Proof: No H5/H6 Report Production/Public True Strings

```
h5_h6_report_lock_violations []
```

Audit scan confirmed: no H5 or H6 reports contain production_ready set to true or public_claim_allowed set to true.

## Proof: production_ready=false

- All dry-run contract outputs include `"production_ready": false`
- Test T31 explicitly verifies this
- `h6_1_shadow_local_adapter_dry_run_not_production` is a permanent reason

## Proof: public_claim_allowed=false

- All dry-run contract outputs include `"public_claim_allowed": false`
- Test T31 explicitly verifies this
- `public_claim_blocked` is a permanent reason

## Statements

- **Shadow adapter dry-run only**: H6-1 simulates the adapter invocation path without executing real operations
- **Not production ready**: H6-1 dry-run is a validation receipt, not a production deployment
- **Not public claim safe**: No public claims can be made based on H6-1 dry-run results alone

## Allowed Shadow Modes

- dry_run
- trace_only

## Allowed Receipt Statuses

- dry_run_only
- trace_only

## Allowed Model Roles

- selector
- localizer
- patch_synthesizer
- verifier_assist

## Allowed Model Families

- qwen

## Allowed Model Sizes

- 3b, 7b, 14b

## Allowed Route Modes

- local_first, local_only, shadow_only

## H6-1 Gate Logic

```
dry_run_allowed = flag AND preflight_present AND preflight_ready AND adapter_contract_ready AND ready_dry AND preflight_safety == 0
dry_run_ready = dry_run_allowed AND valid_requests > 0 AND valid_receipts > 0 AND safety == 0
adapter_dry_run_receipt_ready = dry_run_ready AND valid_requests >= 1 AND valid_receipts >= 1 AND invalid_requests == 0 AND invalid_receipts == 0
ready_io = adapter_dry_run_receipt_ready AND mc_count == 0 AND ol_count == 0 AND cl_count == 0 AND rm_count == 0 AND bh_count == 0
```
