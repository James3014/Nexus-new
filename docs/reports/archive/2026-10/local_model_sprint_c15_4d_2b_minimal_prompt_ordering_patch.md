# LocalHeal Sprint C15-4D-2B: Minimal Prompt Ordering Patch

**Status**: `C15_4D_2B_MINIMAL_PROMPT_ORDERING_PATCH_PASS`

**Date**: 2026-07-04

**Base commit**: `24dea18b0 test(localheal): add delegated retry prompt ordering guard`

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/prompt_builder.py` | Reordered `build_verification_guided_retry_prompt` return statement (line 300) |
| `docs/reports/local_model_sprint_c15_4d_2b_minimal_prompt_ordering_patch.md` | This report |

---

## Exact Production Change

**Before** (prompt_builder.py:300):
```python
return original_user_prompt + header + verifier_section + evidence_section + search_lock + instruction
```

**After** (prompt_builder.py:300-308):
```python
reminder = (
    "\n\nREMINDER: Output one SEARCH/REPLACE block. "
    "Keep the SEARCH block exactly as shown above. "
    "Fix only the REPLACE block.\n"
)

return original_user_prompt + header + search_lock + instruction + verifier_section + evidence_section + reminder
```

---

## Before/After Prompt Ordering

| Position | Before | After |
|----------|--------|-------|
| 1 | original_user_prompt | original_user_prompt |
| 2 | header | header |
| 3 | **verifier_section** | **search_lock** |
| 4 | **evidence_section** | **instruction** |
| 5 | **search_lock** | **verifier_section** |
| 6 | **instruction** | **evidence_section** |
| 7 | — | **reminder** (new, short) |

Rationale: Locked SEARCH and output format instruction now appear before verifier evidence. Small local models see the structural contract first, reducing positional bias toward logic-only fixes.

---

## Tests Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/prompt_builder.py \
  tests/unit/local_heal/test_prompt_builder.py
# exit 0

uv run pytest tests/unit/local_heal/test_prompt_builder.py -v
# 5 passed

uv run pytest tests/unit/local_heal -q --timeout=30
# 905 passed, 16 failed (pre-existing), 1 skipped
```

---

## Test Results

### Prompt Builder Tests (this task)

| Test | Result |
|------|--------|
| `test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence` | ✅ PASS |
| `test_verification_guided_retry_prompt_keeps_output_format_near_locked_search` | ✅ PASS |
| `test_verification_guided_retry_prompt_preserves_verifier_evidence` | ✅ PASS |
| `test_primary_patch_system_prompt_unchanged` | ✅ PASS |
| `test_no_route_authority_fields_change` | ✅ PASS |

### Broader local_heal Suite

- **905 passed**, 16 failed (pre-existing), 1 skipped
- 16 failures are all pre-existing and unrelated to prompt ordering:
  - `test_bmf3_nexus_memory_integration` (1) — memory trace status
  - `test_candidate_decision_autoreason` (2) — ddtree/autoreason ranking
  - `test_decoupled_architecture_tdd` (1) — slim prompt length assertion
  - `test_external_primary_local_assist_three_arm` (1) — three-arm benchmark
  - `test_memory_eval_*` (5) — memory retrieval precision
  - `test_patch_applier` (3) — match_authority, canonical_span, closest_match
  - `test_real_capability_wiring` (1) — claim_gate adapter
  - `test_receipt_v1_schema` (2) — claim_eligible verification

None of these failures are caused by the prompt ordering change.

---

## Blast Radius

| 層面 | 影響 |
|------|------|
| `build_verification_guided_retry_prompt` | ✅ Modified — reordered sections |
| `build_patch_system_prompt` | ❌ Unchanged |
| `build_patch_user_prompt` | ❌ Unchanged |
| System prompt | ❌ Unchanged |
| Parser/verifier | ❌ Unchanged |
| Candidate isolation | ❌ Unchanged |
| Route/topology | ❌ Unchanged |
| Orchestrator | ❌ Unchanged (consumes same function) |

---

## Statements

- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **Parser/verifier/candidate isolation unchanged**: No changes to these systems.
- **No benchmark behavior changed**: No benchmark code modified.
- **No live benchmark run**: This task only ran unit tests.
- **delegated_retry solved NOT_PROVEN**: This task does not prove delegated_retry solved. Prompt ordering is a hypothesis — bounded live recheck needed.
- **production_ready=false**: This minimal patch is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.

---

## Next Recommended Task

**C15-4D-2C Bounded Delegated Retry Recheck**

Run bounded live probe with `toy-math-verifier-evidence-gap` to verify whether the prompt reordering improves delegated retry output quality (reduces INDENTATION_SYNTAX_ERROR / SEARCH_MISMATCH). If recheck passes, proceed to C15-4E Claim Boundary.
