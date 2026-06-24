# H6-2: Adapter IO Schema Test

**Status**: H6_2_ADAPTER_IO_SCHEMA_TEST_PASS

## Summary

H6-2 validates local adapter input/output schema envelopes for Qwen local adapter integration. This phase ensures the adapter IO schema, envelope structure, side-effect locks, and receipt compatibility are correctly defined. H6-2 does not call real Qwen models, does not invoke Ollama, and does not perform real inference.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 37 H6-2 tests (T01-T41)
- `scripts/bench/capability_ab_runner.py` — Added `_build_h6_adapter_io_schema_test` helper function + summary counters
- `docs/reports/h6_2_adapter_io_schema_test_v0.md` — This report

## Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_2" --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_2" -q
NEXUS_H6_ALLOW_ADAPTER_IO_SCHEMA_TEST=1 python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_2" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_1 or h6_2" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

- H6-2 collect-only: 37 selected
- H6-2 targeted default env: 37 passed
- H6-2 flagged env: 37 passed
- H6-1/H6-2 targeted: 71 passed
- H5/H6 selector suite: 578 passed
- Local smoke: 38 passed
- Cloud smoke: 18 passed

## Adapter IO Schema

The schema is `nexus.hybrid_h6_adapter_io_schema_test.v1`. All outputs include:
- `evaluated: true`
- `io_schema_status: adapter_io_schema_ready | adapter_io_schema_fail | blocked`
- `production_ready: false`
- `public_claim_allowed: false`

## Valid IO Examples

### Qwen 3B Selector

**Input Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```

**Output Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "output_status": "schema_only",
  "output_ref": "fixture://output-001"
}
```

### Qwen 7B Localizer

**Input Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-002",
  "adapter_id": "qwen7b-localizer-v0",
  "model_family": "qwen",
  "model_size": "7b",
  "model_name": "qwen2.5-coder:7b",
  "role": "localizer",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-002"
}
```

**Output Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-002",
  "adapter_id": "qwen7b-localizer-v0",
  "output_status": "schema_only",
  "output_ref": "fixture://output-002"
}
```

### Qwen 14B Patch Synthesizer

**Input Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-003",
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "model_family": "qwen",
  "model_size": "14b",
  "model_name": "qwen2.5-coder:14b",
  "role": "patch_synthesizer",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-003"
}
```

**Output Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-003",
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "output_status": "schema_only",
  "output_ref": "fixture://output-003"
}
```

### Verifier Assist

**Input Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-004",
  "adapter_id": "qwen3b-verifier-assist-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "verifier_assist",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-004"
}
```

**Output Envelope**:
```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-004",
  "adapter_id": "qwen3b-verifier-assist-v0",
  "output_status": "schema_only",
  "output_ref": "fixture://output-004"
}
```

## Invalid Input Examples

### Missing Request ID

```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```
**Result**: `missing_request_id` reason, input invalid

### Missing Adapter ID

```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-001",
  "adapter_id": "",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```
**Result**: `missing_adapter_id` reason, input invalid

### Missing Model Name

```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```
**Result**: `missing_model_name` reason, input invalid

### Missing Role

```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "proposer",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```
**Result**: `missing_role` reason, input invalid

### Missing Input Ref

```json
{
  "schema_version": "nexus.local_adapter.input.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": ""
}
```
**Result**: `missing_input_ref` reason, input invalid

### Invalid Input Schema Version

```json
{
  "schema_version": "invalid.version",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "input_ref": "fixture://case-001"
}
```
**Result**: `invalid_schema_version` reason, input invalid

## Invalid Output Examples

### Missing Output Ref

```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "output_status": "schema_only",
  "output_ref": ""
}
```
**Result**: `missing_output_ref` reason, output invalid

### Invalid Output Schema Version

```json
{
  "schema_version": "invalid.version",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "output_status": "schema_only",
  "output_ref": "fixture://output-001"
}
```
**Result**: `invalid_schema_version` reason, output invalid

### Invalid Output Status

```json
{
  "schema_version": "nexus.local_adapter.output.v1",
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "output_status": "production",
  "output_ref": "fixture://output-001"
}
```
**Result**: `invalid_output_status` reason, output invalid

## Unmatched IO Examples

Input with request_id "io-req-001" matched against output with request_id "io-req-002":
- `unmatched_input_count`: 1
- `unmatched_output_count`: 1
- `matched_io_pair_count`: 0

## Side-Effect Blocker Examples

### Model Call Executed

```json
{
  "model_call_executed": true,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false,
  "runtime_effect": false
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
  "behavior_changed": false,
  "runtime_effect": false
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
  "behavior_changed": false,
  "runtime_effect": false
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
  "behavior_changed": false,
  "runtime_effect": false
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
  "behavior_changed": true,
  "runtime_effect": false
}
```
**Result**: `behavior_changed_detected` reason, safety_violation_count=1

### Runtime Effect

```json
{
  "model_call_executed": false,
  "ollama_invoked": false,
  "cloud_invoked": false,
  "repo_mutated": false,
  "behavior_changed": false,
  "runtime_effect": true
}
```
**Result**: `runtime_effect_detected` reason, safety_violation_count=1

## Proof: No Model Calls Executed

- All valid input/output envelopes have `model_call_executed: false`
- Test T29 verifies detection of `model_call_executed: true` triggers failure
- Audit scan confirms no test functions execute real model calls

## Proof: No Ollama Invocation

- All valid input/output envelopes have `ollama_invoked: false`
- Test T30 verifies detection of `ollama_invoked: true` triggers failure
- `ollama_invocation_blocked` is a permanent reason in IO schema output

## Proof: No Cloud Invocation

- All valid input/output envelopes have `cloud_invoked: false`
- Test T31 verifies detection of `cloud_invoked: true` triggers failure
- `cloud_invocation_blocked` is a permanent reason in IO schema output

## Proof: No Repo Mutation

- All valid input/output envelopes have `repo_mutated: false`
- Test T32 verifies detection of `repo_mutated: true` triggers failure
- `repo_mutation_blocked` is a permanent reason in IO schema output

## Proof: No Runtime Effect

- All valid input/output envelopes have `runtime_effect: false`
- Test T34 verifies detection of `runtime_effect: true` triggers failure
- `runtime_effect_blocked` is a permanent reason in IO schema output

## Proof: ready_for_h6_3_shadow_adapter_routing Can Become True

- Tests T11-T14 demonstrate: when all conditions met, `ready_for_h6_3_shadow_adapter_routing` is True
- Condition: adapter_io_schema_ready AND safety_violation_count == 0

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

- All IO schema outputs include `"production_ready": false`
- Test T36 explicitly verifies this
- `h6_2_adapter_io_schema_test_not_production` is a permanent reason

## Proof: public_claim_allowed=false

- All IO schema outputs include `"public_claim_allowed": false`
- Test T36 explicitly verifies this
- `public_claim_blocked` is a permanent reason

## Statements

- **Adapter IO schema only**: H6-2 validates the adapter IO schema without executing real operations
- **Not production ready**: H6-2 IO schema test is a validation gate, not a production deployment
- **Not public claim safe**: No public claims can be made based on H6-2 IO schema test results alone

## Allowed Input Schema Version

- nexus.local_adapter.input.v1

## Allowed Output Schema Version

- nexus.local_adapter.output.v1

## Allowed Output Statuses

- schema_only
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

## H6-2 Gate Logic

```
io_schema_allowed = flag AND shadow_present AND shadow_ready AND receipt_ready AND ready_io AND shadow_safety == 0
io_schema_ready = io_schema_allowed AND valid_inputs > 0 AND valid_outputs > 0 AND matched_io_pair_count > 0 AND safety == 0
adapter_io_schema_ready = io_schema_ready AND invalid_inputs == 0 AND invalid_outputs == 0 AND matched_io_pair_count >= 1
ready_routing = adapter_io_schema_ready AND mc_count == 0 AND ol_count == 0 AND cl_count == 0 AND rm_count == 0 AND bh_count == 0 AND re_count == 0
```
