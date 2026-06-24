# H6-3: Shadow Adapter Routing

**Status**: H6_3_SHADOW_ADAPTER_ROUTING_PASS

## Summary

H6-3 routes validated H6-2 adapter IO envelopes into a shadow local adapter routing decision. This phase ensures Nexus can select a shadow local adapter route from valid adapter IO envelopes and produce a routing receipt. H6-3 does not call real Qwen models, does not invoke Ollama, and does not perform real inference.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 42 H6-3 tests (T01-T44)
- `scripts/bench/capability_ab_runner.py` — Added `_build_h6_shadow_adapter_routing` helper function + summary counters
- `docs/reports/h6_3_shadow_adapter_routing_v0.md` — This report

## Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_3" --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_3" -q
NEXUS_H6_ALLOW_SHADOW_ADAPTER_ROUTING=1 python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_3" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_2 or h6_3" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

- H6-3 collect-only: 42 selected
- H6-3 targeted default env: 42 passed
- H6-3 flagged env: 42 passed
- H6-2/H6-3 targeted: 79 passed
- H5/H6 selector suite: 620 passed
- Local smoke: 38 passed
- Cloud smoke: 18 passed

## Shadow Adapter Routing Schema

The schema is `nexus.hybrid_h6_shadow_adapter_routing.v1`. All outputs include:
- `evaluated: true`
- `routing_status: shadow_adapter_routing_ready | shadow_adapter_routing_fail | blocked`
- `production_ready: false`
- `public_claim_allowed: false`

## Valid Route Examples

### Qwen 3B Selector (Selected)

**Route Candidate**:
```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

**Routing Receipt**:
```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "routing_status": "shadow_route_selected",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

### Qwen 7B Localizer (Selected)

**Route Candidate**:
```json
{
  "request_id": "io-req-002",
  "adapter_id": "qwen7b-localizer-v0",
  "model_family": "qwen",
  "model_size": "7b",
  "model_name": "qwen2.5-coder:7b",
  "role": "localizer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

**Routing Receipt**:
```json
{
  "request_id": "io-req-002",
  "adapter_id": "qwen7b-localizer-v0",
  "routing_status": "shadow_route_selected",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

### Qwen 14B Patch Synthesizer (Selected)

**Route Candidate**:
```json
{
  "request_id": "io-req-003",
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "model_family": "qwen",
  "model_size": "14b",
  "model_name": "qwen2.5-coder:14b",
  "role": "patch_synthesizer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

**Routing Receipt**:
```json
{
  "request_id": "io-req-003",
  "adapter_id": "qwen14b-patch-synthesizer-v0",
  "routing_status": "shadow_route_selected",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

### Verifier Assist (Selected)

**Route Candidate**:
```json
{
  "request_id": "io-req-004",
  "adapter_id": "qwen3b-verifier-assist-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "verifier_assist",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

**Routing Receipt**:
```json
{
  "request_id": "io-req-004",
  "adapter_id": "qwen3b-verifier-assist-v0",
  "routing_status": "shadow_route_selected",
  "routing_mode": "shadow_route_only",
  "route_selected": true
}
```

## Blocked Route Example

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "routing_status": "shadow_route_blocked",
  "routing_mode": "shadow_route_only",
  "route_selected": false
}
```

## Invalid Candidate Examples

### Missing Request ID

```json
{
  "request_id": "",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `missing_request_id` reason, candidate invalid

### Missing Adapter ID

```json
{
  "request_id": "io-req-001",
  "adapter_id": "",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `missing_adapter_id` reason, candidate invalid

### Missing Model Name

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `missing_model_name` reason, candidate invalid

### Missing Role

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "proposer",
  "route_mode": "shadow_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `missing_role` reason, candidate invalid

### Missing Route Mode

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "cloud_only",
  "adapter_mode": "shadow_only",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `missing_route_mode` reason, candidate invalid

### Invalid Adapter Mode

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "model_family": "qwen",
  "model_size": "3b",
  "model_name": "qwen2.5-coder:3b",
  "role": "selector",
  "route_mode": "shadow_only",
  "adapter_mode": "production",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `invalid_adapter_mode` reason, candidate invalid

## Invalid Receipt Example

### Invalid Routing Status

```json
{
  "request_id": "io-req-001",
  "adapter_id": "qwen3b-selector-v0",
  "routing_status": "invalid_status",
  "routing_mode": "shadow_route_only"
}
```
**Result**: `invalid_routing_receipt` reason, receipt invalid

## Unmatched Route Examples

Candidate with request_id "io-req-001" matched against receipt with request_id "io-req-002":
- `shadow_route_selected_count`: 0
- `ready_for_h6_4_local_adapter_execution_plan_dry_run`: false

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

- All valid route candidates/receipts have `model_call_executed: false`
- Test T32 verifies detection of `model_call_executed: true` triggers failure
- Audit scan confirms no test functions execute real model calls

## Proof: No Ollama Invocation

- All valid route candidates/receipts have `ollama_invoked: false`
- Test T33 verifies detection of `ollama_invoked: true` triggers failure
- `ollama_invocation_blocked` is a permanent reason in routing output

## Proof: No Cloud Invocation

- All valid route candidates/receipts have `cloud_invoked: false`
- Test T34 verifies detection of `cloud_invoked: true` triggers failure
- `cloud_invocation_blocked` is a permanent reason in routing output

## Proof: No Repo Mutation

- All valid route candidates/receipts have `repo_mutated: false`
- Test T35 verifies detection of `repo_mutated: true` triggers failure
- `repo_mutation_blocked` is a permanent reason in routing output

## Proof: No Runtime Effect

- All valid route candidates/receipts have `runtime_effect: false`
- Test T37 verifies detection of `runtime_effect: true` triggers failure
- `runtime_effect_blocked` is a permanent reason in routing output

## Proof: ready_for_h6_4_local_adapter_execution_plan_dry_run Can Become True

- Tests T13-T16 demonstrate: when all conditions met, `ready_for_h6_4_local_adapter_execution_plan_dry_run` is True
- Condition: shadow_adapter_routing_receipt_ready AND safety_violation_count == 0

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

- All routing outputs include `"production_ready": false`
- Test T39 explicitly verifies this
- `h6_3_shadow_adapter_routing_not_production` is a permanent reason

## Proof: public_claim_allowed=false

- All routing outputs include `"public_claim_allowed": false`
- Test T39 explicitly verifies this
- `public_claim_blocked` is a permanent reason

## Statements

- **Shadow adapter routing only**: H6-3 routes validated adapter IO envelopes without executing real operations
- **Not production ready**: H6-3 routing is a validation gate, not a production deployment
- **Not public claim safe**: No public claims can be made based on H6-3 routing results alone

## Allowed Routing Modes

- shadow_route_only
- trace_only

## Allowed Routing Statuses

- shadow_route_selected
- shadow_route_blocked
- trace_only

## Allowed Route Modes

- shadow_only
- local_first
- local_only

## Allowed Adapter Modes

- shadow_only

## Allowed Model Roles

- selector
- localizer
- patch_synthesizer
- verifier_assist

## Allowed Model Families

- qwen

## Allowed Model Sizes

- 3b, 7b, 14b

## H6-3 Gate Logic

```
routing_allowed = flag AND io_schema_present AND io_schema_ready AND adapter_io_schema_ready AND ready_routing AND io_safety == 0
routing_ready = routing_allowed AND valid_candidates > 0 AND valid_receipts > 0 AND matched_rids > 0 AND safety == 0
receipt_ready = routing_ready AND invalid_candidates == 0 AND invalid_receipts == 0 AND shadow_selected >= 1
ready_exec = receipt_ready AND mc_count == 0 AND ol_count == 0 AND cl_count == 0 AND rm_count == 0 AND bh_count == 0 AND re_count == 0
```
