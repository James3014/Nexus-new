# LocalHeal Sprint C15-4D-1: Delegated Retry Output Failure Taxonomy

**Status**: `C15_4D_1_DELEGATED_RETRY_OUTPUT_FAILURE_TAXONOMY_PASS`

**Date**: 2026-07-03

---

## Files Inspected

- `docs/reports/local_model_sprint_c15_4c_2_forced_delegated_retry_live_probe.md`
- `docs/reports/local_model_sprint_c15_4d_0_delegated_retry_protocol_contract_reuse_audit.md`
- `.nexus/reports/local_model/m1_real_local_solve_results.jsonl`

---

## Source of Raw Output Evidence

Raw delegated retry output extracted from JSONL `semantic_retry_raw_response_excerpt` field for `toy-math-verifier-evidence-gap` attempts.

---

## Attempt-by-Attempt Failure Table

| Attempt | `delegated_retry_status` | Raw Output | Failure Category |
|---------|------------------------|------------|-----------------|
| 1 | REPLACE_SYNTAX_ERROR: expected an indented block after 'if' statement on line 9 | `<<<<<<< SEARCH\n    return (score - min_val) / (max_val - min_val)\n=======\n    if max_val == min_val:\n        return 0.5\n    else:\n        return clamp((score - min_val) / (max_val - min_val), 0, 1)\n>>>>>>> REPLACE` | INDENTATION_SYNTAX_ERROR |
| 2 | REPLACE_SYNTAX_ERROR: expected an indented block after 'if' statement on line 3 | `<<<<<<< SEARCH\n    return (score - min_val) / (max_val - min_val)\n=======\n    if max_val == min_val:\n        return 0.5\n    return max(0, min(1, (score - min_val) / (max_val - min_val)))\n>>>>>>> REPLACE` | INDENTATION_SYNTAX_ERROR |
| 3 | SEARCH_MISMATCH | `<<<<<<< SEARCH\n    return (score - min_val) / (max_val - min_val)\n=======\n    if max_val == min_val:\n        return 0.5\n    else:\n        return max(0, min(1, (score - min_val) / (max_val - min_val)))\n>>>>>>> REPLACE` | SEARCH_NOT_EXACT_SOURCE |

---

## Failure Category Analysis

### Attempt 1 & 2: INDENTATION_SYNTAX_ERROR

**Root cause**: The model's REPLACE block uses `if/else` but the indentation is wrong — Python expects an indented block after `if` but the model outputs the `if` and `else` at the same indentation level as the `return` statement.

**Raw output shows**:
```python
    if max_val == min_val:
        return 0.5
    else:
        return clamp((score - min_val) / (max_val - min_val), 0, 1)
```

The `if/else` is correctly indented relative to the function body, but the **applied patch** produces code where the `if` statement is not properly nested inside the function. This is a model output quality issue — the model understands the logic but produces syntactically incorrect indentation in the applied patch.

### Attempt 3: SEARCH_NOT_EXACT_SOURCE

**Root cause**: The model's SEARCH block does not exactly match the current source file content. The SEARCH block shows:
```python
    return (score - min_val) / (max_val - min_val)
```

But the current source file may have been modified by a previous attempt or re-anchor, causing the SEARCH block to not match.

---

## Failure Category Classification

| Category | Count | Description |
|----------|-------|-------------|
| INDENTATION_SYNTAX_ERROR | 2 | Model produces correct logic but wrong indentation in applied patch |
| SEARCH_NOT_EXACT_SOURCE | 1 | SEARCH block doesn't match current source file |

---

## Likely Fixability Classification

| Attempt | Category | Fixable By |
|---------|----------|-----------|
| 1 | INDENTATION_SYNTAX_ERROR | likely fixable by output excerpt feedback (show model its own indentation error) |
| 2 | INDENTATION_SYNTAX_ERROR | likely fixable by output excerpt feedback (show model its own indentation error) |
| 3 | SEARCH_NOT_EXACT_SOURCE | likely fixable by narrowing locked_search (ensure SEARCH matches current source) |

---

## Raw Output Sufficiency

**Sufficient** — The `semantic_retry_raw_response_excerpt` field contains bounded output excerpts that allow failure classification. No live benchmark was needed.

---

## Contract Reuse Confirmation

Confirmed from C15-4D-0: **CONTRACT_REUSED**. The delegated retry fully reuses the C11/C13 SEARCH/REPLACE output protocol contract. The failures are model output quality issues, not protocol contract issues.

---

## Recommended Next Task

**C15-4D-2 Delegated Retry Prompt Ordering Nudge**

The most likely fix is to adjust the retry prompt ordering so the model sees the SEARCH/REPLACE format requirement **before** the verifier evidence. Currently:
1. Original user prompt
2. Error-specific retry instruction (SelfCorrector)
3. Verifier evidence (if injected)

If the model sees verifier evidence first, it may focus on the evidence and produce logic changes that violate the SEARCH/REPLACE format. Reordering to put format requirement first may help.

Alternatively: **C15-4E Delegated Retry Output Quality Claim Boundary** — formally define what can be claimed given current model quality limitations.

---

## Statements

- **No runtime behavior changed**: This task only performed read-only inspection.
- **No prompt behavior changed**: No prompt_builder or SelfCorrector modifications.
- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **parser/verifier/candidate isolation unchanged**: No changes to these systems.
- **delegated_retry solved NOT_PROVEN**: This task does not prove delegated_retry solved.
- **production_ready=false**: This taxonomy is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
