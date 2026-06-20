# T2.0 Report Cleanup

**日期**: 2026-06-17

---

## T2.0 Verdict: 🟢 Green with workspace caveat

### Corrected Wording

| Original (incorrect) | Corrected |
|---|---|
| 5/5 fully solved | 4/4 configured tasks solved, 1 workspace_not_configured |
| Qwen solved 4/5 | Deterministic/canonical recovery solved 4/4 configured tasks |
| model capability improved | Hybrid canonical span extraction proven effective |
| sympy-12481 patcher failed | sympy-12481 workspace_not_configured (Python 3.14 incompatible) |

---

### Full 5-task coverage

| Task | Status | failure_class |
|---|---|---|
| astropy-12907 | ✅ solved | SOLVED |
| astropy-13236 | ✅ solved | SOLVED |
| astropy-13579 | ✅ solved | SOLVED |
| astropy-14182 | ✅ solved | SOLVED |
| sympy-12481 | ❌ workspace_not_configured | workspace_not_configured |

---

### Key clarifications

- **sympy-12481 is workspace_not_configured**, not patcher failure
- **No SEARCH_MISMATCH regression**
- **No model_calls=0 counted as model success**
- **public_claim_allowed=false** for all tasks
- **claim_eligible=false** for all tasks (focused internal regression)

---

### Attribution

| Task | model_calls | model_patch_reward | deterministic_fallback_reward |
|---|---|---|---|
| astropy-12907 | 0 | 0.0 | AST_SYMBOL_FIX |
| astropy-13236 | 0 | 0.0 | REMOVE_BLOCK |
| astropy-13579 | 0 | 0.0 | — |
| astropy-14182 | 0 | 0.0 | — |
| sympy-12481 | 0 | 0.0 | — (workspace fail) |

---

### Export eligibility

| Task | export_as_model_patch_success | export_as_canonical_recovery_success | export_as_internal_infra_failure |
|---|---|---|---|
| astropy-12907 | false | true | false |
| astropy-13236 | false | true | false |
| astropy-13579 | false | true | false |
| astropy-14182 | false | true | false |
| sympy-12481 | false | false | true |
