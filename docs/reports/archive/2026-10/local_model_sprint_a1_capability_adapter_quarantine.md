# Local Model Sprint A1: Capability Adapter Quarantine Guard

**Status:** LOCAL_MODEL_SPRINT_A1_CAPABILITY_ADAPTER_QUARANTINE_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `tests/unit/local_heal/test_capability_adapter.py` | Added 5 quarantine guard tests |
| `docs/reports/local_model_sprint_a1_capability_adapter_quarantine.md` | Report |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_capability_adapter.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 24 passed
```

## Test Counts

- `test_capability_adapter.py`: 17 passed (11 legacy + 5 quarantine + 1 default)
- `test_downstream_enforcement_gates.py`: 8 passed

## Remaining RouteMode Constructors

All 16 `RouteMode` constructors in `capability_adapter.py` hardcode `route_truth_source="CapabilityPlanner"` and `adapter_output_is_route_truth=False`. None read from controls or payload.

## Why Remaining Constructors Are Non-Authoritative

Every `build_hybrid_route_decision` call in the adapter passes:
- `route_truth_source="CapabilityPlanner"` (hardcoded string)
- `adapter_output_is_route_truth=False` (hardcoded bool)
- `public_claim_allowed=False` (hardcoded bool)
- `production_ready=False` (hardcoded bool)
- `behavior_changed=False` (hardcoded bool)

No path reads these from `controls`, `payload`, or `os.environ`.

## Quarantine Verification

| Guard | Status |
|-------|--------|
| Fail closed on missing signal_snapshot | ✅ Verified |
| route_truth_source frozen to CapabilityPlanner | ✅ Verified |
| adapter_output_is_route_truth always False | ✅ Verified |
| Env flag does not create route authority | ✅ Verified |
| Cannot synthesize signal_snapshot from env | ✅ Verified |

## Explicit Statements

- No new route added.
- No adapter route authority.
- Step 5 quarantine guard complete.
- capability_adapter remains legacy compatibility shim only.
