# H6-0: Local Model Adapter Preflight Contract

**Status**: H6_0_LOCAL_MODEL_ADAPTER_PREFLIGHT_CONTRACT_PASS

## Summary

H6-0 validates the adapter preflight contract for local model integration. This phase ensures the adapter interface is correctly defined without executing any real model calls, Ollama invocations, cloud invocations, or repository mutations. H6-0 is the entry point from H5 to H6.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 30 H6-0 tests (T01-T30)
- `scripts/bench/capability_ab_runner.py` — Existing `_build_h6_local_model_adapter_preflight_contract` function (no changes needed)
- `docs/reports/h6_0_local_model_adapter_preflight_contract_v0.md` — This report

## Commands Run

```bash
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_0" --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_0" -v --tb=short
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h5_51 or h6_0" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

- H6-0 collect-only: 30 selected
- H6-0 tests: 30 passed
- H5-51/H6-0 targeted: passed
- H5/H6 selector suite: passed
- Local smoke: 38 passed
- Cloud smoke: 18 passed

## Preflight Contract Schema

The contract schema is `nexus.hybrid_h6_local_model_adapter_preflight_contract.v1`. All outputs include:
- `evaluated: true`
- `preflight_status: local_model_adapter_preflight_ready | blocked | local_model_adapter_preflight_fail`
- `production_ready: false`
- `public_claim_allowed: false`

## Valid Candidate Examples

### Qwen 3B Selector

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "3b",
  "role": "selector",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only",
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false
}
```

### Qwen 7B Localizer

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "7b",
  "role": "localizer",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only",
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false
}
```

### Qwen 14B Patch Synthesizer

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "14b",
  "role": "patch_synthesizer",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only",
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false
}
```

## Invalid Candidate Examples

### Invalid Family (llama)

```json
{
  "required_fields_present": true,
  "model_family": "llama",
  "model_size": "3b",
  "role": "selector",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only"
}
```
**Result**: `invalid_model_family` reason, preflight_fail

### Invalid Role (proposer)

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "3b",
  "role": "proposer",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only"
}
```
**Result**: `invalid_role` reason, preflight_fail

### Invalid Size (1b)

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "1b",
  "role": "selector",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only"
}
```
**Result**: `invalid_model_size` reason, preflight_fail

### Invalid Route (cloud_only)

```json
{
  "required_fields_present": true,
  "model_family": "qwen",
  "model_size": "3b",
  "role": "selector",
  "route_mode": "cloud_only",
  "adapter_mode": "preflight_only"
}
```
**Result**: `unsafe_route_mode` reason, preflight_fail

### Missing Required Fields

```json
{
  "required_fields_present": false,
  "model_family": "qwen",
  "model_size": "3b",
  "role": "selector",
  "route_mode": "local_first",
  "adapter_mode": "preflight_only"
}
```
**Result**: `missing_required_fields` reason, preflight_fail

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

- All valid candidates have `model_call_executed: false`
- Test T04 verifies detection of `model_call_executed: true` triggers failure
- Test T18 verifies multiple violations aggregate correctly
- Audit scan confirms no test functions execute real model calls

## Proof: No Ollama Invocation

- All valid candidates have `ollama_invoked: false`
- Test T05 verifies detection of `ollama_invoked: true` triggers failure
- `ollama_invocation_blocked` is a permanent reason in preflight output

## Proof: No Cloud Invocation

- All valid candidates have `cloud_invoked: false`
- Test T15 verifies detection of `cloud_invoked: true` triggers failure
- `cloud_invocation_blocked` is a permanent reason in preflight output

## Proof: No Repo Mutation

- All valid candidates have `repo_mutated: false`
- Test T16 verifies detection of `repo_mutated: true` triggers failure
- `repo_mutation_blocked` is a permanent reason in preflight output

## Proof: ready_for_h6_1_shadow_local_adapter_dry_run Can Become True

- Test T02 demonstrates: when all conditions met, `ready_for_h6_1_shadow_local_adapter_dry_run` is True
- Condition: preflight_ready AND safety_violation_count == 0 AND no invalid candidates

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

- All preflight contract outputs include `"production_ready": false`
- Test T20 explicitly verifies this
- `h6_0_local_model_adapter_preflight_not_production` is a permanent reason

## Proof: public_claim_allowed=false

- All preflight contract outputs include `"public_claim_allowed": false`
- Test T20 explicitly verifies this
- `public_claim_blocked` is a permanent reason

## Statements

- **Preflight contract only**: H6-0 validates the adapter interface contract without executing any real operations
- **Not production ready**: H6-0 preflight is a validation gate, not a production deployment
- **Not public claim safe**: No public claims can be made based on H6-0 preflight results alone

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

## Allowed Adapter Modes

- preflight_only, shadow_only

## H6-0 Gate Logic

```
preflight_allowed = flag AND batch_present AND batch_ready AND ready_h6 AND batch_safety == 0
preflight_ready = preflight_allowed AND valid_candidates > 0 AND safety == 0
contract_ready = preflight_ready AND valid_candidates > 0 AND invalid_count == 0
ready_dry = contract_ready AND mc_count == 0 AND ollama_count == 0 AND cloud_count == 0 AND repo_mut == 0 AND beh == 0
```
