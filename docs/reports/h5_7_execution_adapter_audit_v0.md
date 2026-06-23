# H5-7 Execution Adapter Audit Report

**日期**: 2026-06-22
**狀態**: `H5_7_EXECUTION_ADAPTER_AUDIT_COMPLETE`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

Read-only audit. No implementation. No production code changes. No test changes.

## Audited Files

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/bench/capability_ab_runner.py` | 5422-5850, 5859-6040, 8969-9540 | Row finalization, H5 blocks, model calls, evidence bundle |
| `tests/benchmark/test_capability_ab_runner.py` | 1-15900 | H3-H6 tests |
| `nexus/services/local_heal/pipeline.py` | 170-261 | Pipeline run, orchestrator selection |
| `nexus/services/local_heal/committee_orchestrator.py` | 1-303 | U3 committee route |
| `nexus/services/local_heal/receipt.py` | 1-605 | Receipt builder |
| `nexus/services/local_heal/native_route_adapter.py` | 1-248 | Route decision |
| `nexus/services/local_heal/context.py` | 1-97 | HealContext, OperationalContext |
| `nexus/services/local_heal/orchestrator.py` | 1-30 | HealOrchestrator base |

---

## 12 Questions Answered

### Q1: What function currently performs or records model calls?

**`run_with_nexus()`** (line 5859) orchestrates the full with-nexus execution. It calls into the CLI runner which invokes the actual model. `model_calls` is recorded on the row after execution.

**`_run_hybrid_local_guard_trace()`** (line 5353) does NOT make model calls — it reads row fields for advisory trace.

### Q2: Where is the row finalized?

**`_finalize_with_nexus_row()`** (line 5422). This is the single integration point where:
- hybrid_route is built (line 5526)
- local_assist is built (line 5558)
- local_guard is built (line 5576)
- H5-1~H5-6 blocks are attached (lines 5589-5850)
- flat row keys are set (line 5851+)

### Q3: Where is the current provider selected?

**CLI argument `--with-model-provider`** parsed at line 9652-9654, passed into `run_with_nexus()` as `with_model_provider`. Inside `run_with_nexus()`, it becomes the `provider` variable passed to `_finalize_with_nexus_row()`.

### Q4: Where would local-first execution attach without affecting H1-H4 when disabled?

**Inside `_finalize_with_nexus_row()`**, after the H5-6 gate block (line 5850) and before the flat row keys (line 5851).

When `execution_gate_allows_local_first=true` (currently always false):
1. Call `HealPipeline` or `CommitteeOrchestrator` with `NEXUS_USE_COMMITTEE=1`
2. Capture the committee trace
3. Copy U3 fields into h5_route
4. If local solves, set `final_source="local_candidate"`
5. If local fails, proceed to cloud fallback path

This must be gated by a new env flag (e.g., `NEXUS_HYBRID_H5_LOCAL_FIRST_EXECUTION=1`).

### Q5: Where would cloud fallback execution attach without duplicating model calls?

**Inside `_finalize_with_nexus_row()`**, after the local-first path (if implemented) and before flat row keys.

When `execution_gate_allows_cloud_fallback=true`:
1. Re-invoke `run_with_nexus()` or the cloud model path with the local-failed row
2. Capture the cloud output
3. Set `final_source="cloud_fallback"`

Alternatively, cloud fallback could reuse the existing `run_with_nexus()` call by passing a modified row. The key constraint: `model_calls` must be incremented correctly and not double-counted.

### Q6: Where is `final_source` currently absent/present?

`final_source` is ONLY set inside the H5-1 block (line 5642) as `"none"`. It is never set to any other value in the current codebase. The gate reads it from `finalized.get("final_source", "none")`.

### Q7: What exact fields would need to change if local candidate became final?

| Field | Current | After local success |
|-------|---------|-------------------|
| `final_source` | `"none"` | `"local_candidate"` |
| `h5_route.final_source` | `"none"` | `"local_candidate"` |
| `h5_route.local_selected_candidate_applied` | false/true | `true` |
| `h5_route.local_solve_eligible` | false | `true` |
| `h5_route.behavior_changed` | false | `true` |
| `hybrid_route.behavior_changed` | false | `true` |
| `behavior_changed` (row level) | false | `true` |
| `h5_route.cloud_fallback_invoked` | false | false (unchanged) |
| `h5_route.cloud_model_invoked` | false | false (unchanged) |
| Row-level `final_patch` | cloud output | local candidate patch |

### Q8: What exact fields would need to change if cloud fallback became final?

| Field | Current | After cloud fallback |
|-------|---------|-------------------|
| `final_source` | `"none"` | `"cloud_fallback"` |
| `h5_route.final_source` | `"none"` | `"cloud_fallback"` |
| `h5_route.cloud_fallback_invoked` | false | `true` |
| `h5_route.cloud_model_invoked` | false | `true` |
| `h5_route.behavior_changed` | false | `true` |
| `hybrid_route.behavior_changed` | false | `true` |
| `behavior_changed` (row level) | false | `true` |
| Row-level `model_calls` | N | N+1 |
| Row-level `final_patch` | local patch | cloud fallback output |

### Q9: What exact fail-closed conditions must block final_source change?

| Condition | Fail-closed reason |
|-----------|-------------------|
| `cloud_fallback_invoked=true` already set | unexpected_execution_side_effect |
| `cloud_model_invoked=true` already set | unexpected_execution_side_effect |
| `behavior_changed=true` already set | unexpected_execution_side_effect |
| `public_claim_allowed != false` | governance_boundary_violation |
| `production_ready != false` | governance_boundary_violation |
| `blocked_delivery=true` | delivery_blocked |
| Local candidate hash mismatch | local_hash_mismatch |
| Local candidate artifact missing | local_missing_artifact |
| Local candidate mapping missing | local_missing_candidate_mapping |
| Cloud provider unavailable | cloud_provider_unavailable |
| Cloud result unverified | cloud_result_unverified |

### Q10: What new adapter/helper function should H5-8 introduce?

```python
def _build_h5_execution_plan(row: dict[str, Any], *, provider: str) -> dict[str, Any]:
    """Pure function: reads h5_route fields, returns execution plan.
    No side effects. No model calls. No row mutation."""
    ...
```

This function should:
- Read `h5_route` fields from the row
- Read `execution_gate_status` and `execution_gate_allows_*`
- Read `route_order_shadow_terminal_state`
- Return an `h5_execution_plan` dict with planned order, final_source, and governance
- Never mutate the input row

### Q11: What tests must H5-8 add before any execution flag exists?

1. `_build_h5_execution_plan` returns correct plan for each shadow terminal state
2. `_build_h5_execution_plan` returns `execution_allowed=false` when gate is blocked
3. `_build_h5_execution_plan` returns `execution_allowed=false` when all allows_* are false
4. `_build_h5_execution_plan` preserves `public_claim_allowed=false` and `production_ready=false`
5. Existing H5-1~H5-6 tests still pass unchanged
6. `_build_h5_execution_plan` is pure (no side effects verified by test structure)

### Q12: What additional governance fields must remain false until real validation?

| Field | Must remain false until |
|-------|------------------------|
| `public_claim_allowed` | Real cloud E2E validation + quality non-regression |
| `production_ready` | Real cloud E2E + local committee E2E + full benchmark |
| `training_export_allowed` | Separate governance gate |
| `h5_route.behavior_changed` | Actual execution with verified output |
| `h5_route.blocked_delivery` | Actual delivery path tested |
| `h5_route.cloud_fallback_invoked` | Actual cloud fallback executed |
| `h5_route.cloud_model_invoked` | Actual cloud model called |

---

## Proposed Adapter Shape

```python
def _build_h5_execution_plan(row: dict[str, Any], *, provider: str) -> dict[str, Any]:
    """Pure function: builds H5 execution plan from h5_route metadata.
    
    No side effects. No model calls. No row mutation.
    Returns a plan dict that H5-8 can attach as h5_execution_plan.
    """
    h5 = row.get("h5_route", {})
    gate_status = h5.get("execution_gate_status", "not_evaluated")
    shadow_terminal = h5.get("route_order_shadow_terminal_state", "")
    decision = h5.get("cloud_fallback_decision", "")
    allows_local = h5.get("execution_gate_allows_local_first", False)
    allows_cloud = h5.get("execution_gate_allows_cloud_fallback", False)
    
    execution_allowed = False
    execution_mode = "disabled"
    planned_order = []
    planned_final_source = "none"
    requires_local = False
    requires_cloud = False
    requires_output_replace = False
    requires_verifier = True
    requires_claim_gate = True
    fail_closed_reason = ""
    
    if gate_status == "eligible_dry_run_only":
        if shadow_terminal == "would_use_local_candidate" and allows_local:
            execution_mode = "local_candidate_plan"
            planned_order = ["local_committee"]
            planned_final_source = "local_candidate"
            requires_local = True
            requires_output_replace = True
            execution_allowed = True
        elif shadow_terminal == "would_use_cloud_fallback" and allows_cloud:
            execution_mode = "cloud_fallback_plan"
            planned_order = ["local_committee", "cloud_fallback"]
            planned_final_source = "cloud_fallback"
            requires_local = True
            requires_cloud = True
            requires_output_replace = True
            execution_allowed = True
        else:
            execution_mode = "fail_closed_plan"
            fail_closed_reason = "gate_eligible_but_conditions_not_met"
    elif gate_status == "blocked":
        execution_mode = "fail_closed_plan"
        fail_closed_reason = h5.get("execution_gate_reasons", ["unknown"])[0] if h5.get("execution_gate_reasons") else "unknown"
    else:
        execution_mode = "disabled"
    
    return {
        "schema": "nexus.hybrid_h5_execution_plan.v1",
        "execution_allowed": execution_allowed,
        "execution_mode": execution_mode,
        "planned_order": planned_order,
        "planned_final_source": planned_final_source,
        "requires_local_committee": requires_local,
        "requires_cloud_fallback": requires_cloud,
        "requires_output_replacement": requires_output_replace,
        "requires_verifier": requires_verifier,
        "requires_claim_gate": requires_claim_gate,
        "fail_closed_reason": fail_closed_reason,
        "governance": {
            "public_claim_allowed": False,
            "production_ready": False,
        },
    }
```

## Proposed Execution Modes

| Mode | Meaning |
|------|---------|
| `disabled` | H5 execution not enabled |
| `dry_run_plan_only` | Plan computed but not executed |
| `local_candidate_plan` | Local candidate would become final |
| `cloud_fallback_plan` | Cloud fallback would become final |
| `fail_closed_plan` | Execution blocked by invariant |

## Proposed H5-8 Scope

### H5-8: Execution Plan Builder Trace

Implement `_build_h5_execution_plan()` and attach `h5_execution_plan` metadata to the row.

**H5-8 may change**:
- `scripts/bench/capability_ab_runner.py` — add `_build_h5_execution_plan()` helper, attach `h5_execution_plan` in H5 block
- `tests/benchmark/test_capability_ab_runner.py` — add tests for `_build_h5_execution_plan()`
- `docs/reports/h5_8_execution_plan_builder_v0.md`

**H5-8 must not change**:
- `nexus/services/local_heal/committee_orchestrator.py`
- `nexus/services/local_heal/receipt.py`
- `nexus/services/local_heal/pipeline.py`
- `nexus/services/local_heal/native_route_adapter.py`
- `nexus/services/local_heal/context.py`
- `nexus/services/local_heal/orchestrator.py`

---

## Statements

```text
Audit/spec only.
No implementation.
No production code changes.
No test changes.
No H5 execution enabled.
No cloud fallback execution.
No final delivery source change.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
