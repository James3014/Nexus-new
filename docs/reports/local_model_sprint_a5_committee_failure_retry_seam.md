# Local Model Sprint A5: Committee Parse Failure to Retry Path

**Status:** LOCAL_MODEL_SPRINT_A5_COMMITTEE_FAILURE_RETRY_SEAM_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added retry metadata wiring for committee parse failures |
| `tests/unit/local_heal/test_committee_to_repair_seam_audit.py` | Added 5 A5 retry seam tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_committee_to_repair_seam_audit.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 43 passed
```

## Test Counts

- `test_committee_to_repair_seam_audit.py`: 10 passed (5 existing + 5 new)
- `test_local_model_executor.py`: 25 passed
- `test_downstream_enforcement_gates.py`: 8 passed

## Before/After Path

| Condition | Before A5 | After A5 |
|-----------|-----------|----------|
| Committee parse failure | Returns empty hash, no retry metadata | Returns empty hash + retry_available=true + error_kind |
| retry_available | Not tracked | Tracked in raw_meta |
| retry_not_invoked_reason | Not tracked | Tracked when feedback builder unavailable |
| protocol_parse_failed | Not in raw_meta | Added to raw_meta |
| protocol_parse_error_kind | Not in raw_meta | Added to raw_meta |

## Explicit Statements

- No parser/sanitizer change.
- No new route/topology.
- Empty hash still not solved.
- Verifier pass required for solved.
- Retry metadata is observational — does not trigger automatic retry in this stage.
