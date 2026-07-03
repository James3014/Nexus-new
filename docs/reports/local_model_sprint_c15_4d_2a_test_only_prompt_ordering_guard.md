# LocalHeal Sprint C15-4D-2A: Test-only Prompt Ordering Guard

**Status**: `C15_4D_2A_TEST_ONLY_GUARD_RED`

**Date**: 2026-07-04

**Base commit**: `0fc42f69e docs: plan delegated retry prompt ordering diagnosis`

---

## Files Changed

| File | Change |
|------|--------|
| `tests/unit/local_heal/test_prompt_builder.py` | Created — 5 RED/guard tests for delegated retry prompt ordering |

---

## Tests Added

| Test | Purpose | Result |
|------|---------|--------|
| `test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence` | Guard: locked SEARCH must appear before verifier evidence | **RED FAIL** |
| `test_verification_guided_retry_prompt_keeps_output_format_near_locked_search` | Guard: output format instruction near locked SEARCH | PASS |
| `test_verification_guided_retry_prompt_preserves_verifier_evidence` | Guard: verifier evidence not removed | PASS |
| `test_primary_patch_system_prompt_unchanged` | Guard: primary prompt unaffected | PASS |
| `test_no_route_authority_fields_change` | Guard: no route/topology authority introduced | PASS |

---

## Commands Run

```bash
python3 -m py_compile tests/unit/local_heal/test_prompt_builder.py
# exit 0

uv run pytest tests/unit/local_heal/test_prompt_builder.py -v
# 1 failed, 4 passed
```

---

## Exact Test Result

```
FAILED tests/unit/local_heal/test_prompt_builder.py::test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence

AssertionError: Expected search_lock at position 908 to appear BEFORE
verifier_section at position 165. Current ordering: verifier_section
BEFORE search_lock.

assert 908 < 165
```

**Current production ordering** (`prompt_builder.py:300`):
```
original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction
```

- `verifier_section` at position 165
- `search_lock` at position 908

**Desired ordering**:
```
original_user_prompt + header + search_lock + instruction + verifier_section + evidence_section
```

---

## RED/PASS Status

**RED** — 1 intended RED test fails under current production code. This is expected and confirms the guard is effective.

---

## Statements

- **Test-only**: No production code changed. Only `tests/unit/local_heal/test_prompt_builder.py` created.
- **No prompt behavior changed**: `prompt_builder.py` untouched.
- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **delegated_retry solved NOT_PROVEN**: This task does not prove delegated_retry solved.
- **production_ready=false**: This test-only guard is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.

---

## Next Recommended Task

**C15-4D-2B Minimal Prompt Ordering Patch**

The RED test confirms the ordering issue. The minimal patch is:
- Reorder `build_verification_guided_retry_prompt` return statement (prompt_builder.py:300)
- From: `original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction`
- To: `original_user_prompt + header + search_lock + instruction + verifier_section + evidence_section`
- All 5 tests should turn GREEN after the patch.
