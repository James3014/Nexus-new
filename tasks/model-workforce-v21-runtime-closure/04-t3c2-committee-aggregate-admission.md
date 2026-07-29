# T3C2 — Committee Aggregate Admission Wiring

**artifact_authority:** current  
**owner:** James Chen  
**status:** CANDIDATE_READY  
**task_id:** `model-workforce-v21-runtime-closure-t3c2`

## Scope

Evaluate all T3C1 member demands as one policy admission set before any
committee candidate producer/provider call. Missing or malformed binding,
route mismatch, BLOCK, or ESCALATE is represented in the aggregate receipt
and returns zero calls. No member is replaced and no topology or authority is
introduced.

## Evidence

- `COMMITTEE_AGGREGATE_ADMISSION_WIRING_COMPLETE`
- `COMMITTEE_ZERO_CALL_FAIL_CLOSED_VERIFIED`
- aggregate receipt includes per-member decision and reasons
- exact verifier: `uv run pytest -q tests/unit/local_heal/test_c6av_committee_solve_reality_check.py tests/contracts/test_p4_committee_routed_tool_receipts.py`
- exact verifier: `git diff --check`

## Next gate

T3C3 may supply explicit authority-bound bindings and perform physical member
calls only after aggregate `ALLOW`.
