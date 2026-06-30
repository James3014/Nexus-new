# Match Gate Report

**Date**: 2026-06-19 | **Status**: Evidence-ready | **Last verified**: 2026-06-19 08:30 UTC

---

## 1. Regression Gate

| Suite | Command | Result |
|---|---|---|
| `tests/unit/local_heal` | `uv run pytest tests/unit/local_heal -q` | **140 passed** |
| focused receipt/patch | 3 test files | **36 passed** |
| broader regression | 19 test files | **98 passed** |
| broader + focused | combined | **134 passed** |

---

## 2. Verified Repair Receipt (P0)

**Fixture**: `bug_001` — calculator.py `divide()` returns `a*b` instead of `a/b`

| Lane | Model | Role | Patch | Verifier | gate_passed | claim_eligible |
|---|---|---|---|---|---|---|
| 3B | `qwen2.5:3b` | advisor | ✅ applied | ❌ failed | false | false |
| 7B | `qwen2.5-coder:7b` | patch | ✅ applied | ❌ failed | false | false |
| 14B | `qwen2.5-coder:14b-instruct-q3_K_M` | patch | ✅ applied | ✅ **PASSED** | **true** | **true** |

### 14B Verified Repair Details
```
model:          qwen2.5-coder:14b-instruct-q3_K_M
role:           patch
wall_time:      23.4s
tokens:         prompt=54, eval=229, total=283
patch_applied:  true
match_authority: verbatim
verifier:       VERIFICATION PASSED
gate_passed:    true
hidden_passed:  true
claim_eligible: true
public_claim:   false (forbidden)
```

Receipt: `.nexus/reports/local_heal/bug_001_14b_receipt.json`

---

## 3. Three-Lane Smoke (Provider/Evidence)

| Lane | Model | Wall | Tokens | Evidence Gate |
|---|---|---|---|---|
| 3B | `qwen2.5:3b` | 6.78s | 190 | ✅ PASS |
| 7B | `qwen2.5-coder:7b` | 7.24s | 81 | ✅ PASS |
| 14B | `qwen2.5-coder:14b-instruct-q3_K_M` | 14.92s | 96 | ✅ PASS |

---

## 4. Freeze Snapshot

| Category | Claimable | Non-claimable | Total |
|---|---|---|---|
| source | 57 | 0 | 57 |
| tests | 16 | 0 | 16 |
| scripts | 43 | 0 | 43 |
| **Subtotal** | **116** | | |
| benchmarks | 0 | 34 | 34 |
| docs_reports | 0 | 70 | 70 |
| other | 0 | 166 | 166 |
| pycache_build | 0 | 30 | 30 |
| generated_artifacts | 0 | 55 | 55 |
| config | 0 | 2 | 2 |
| **Subtotal** | | **357** | |
| **Total** | **116** | **357** | **473** |

`public_claim_allowed: false`

---

## 5. Claim Boundary

| Claim | Allowed |
|---|---|
| Public SWE-bench | **NO** |
| Local Qwen solve-rate | **NO** |
| Internal evidence | **YES** (14B verified repair on bug_001) |

---

## 6. StrategyEnvelope Fix

Legacy compat fields added to `StrategyEnvelope`. 10/10 strategy tests green. Combined 134 gate restored.

---

## 7. Key Findings

1. **14B can produce verified repairs**: On bug_001, 14B produced correct SEARCH/REPLACE, patch applied, verifier PASSED, `gate_passed=true`, `claim_eligible=true`.
2. **3B/7B not yet reliable**: Both applied patches but verifier failed. 3B role should be advisor only.
3. **CANONICAL_SPAN removed**: Was unreachable dead code.
4. **match_authority telemetry**: Flows through to receipt.
5. **Evidence gate**: All three lanes pass fixture-based evidence gate.

---

## 8. Commands

```bash
# Regression
uv run pytest tests/unit/local_heal -q  # 140
uv run pytest <combined command> -q      # 134

# Evidence gate
python3 -c "from nexus.services.local_heal.local_qwen_evidence_gate import verify_local_qwen_evidence; print(verify_local_qwen_evidence({'provider':'ollama','model_name':'qwen2.5-coder:14b-instruct-q3_K_M','model_calls':1,'provider_token_count':100,'hidden_verifier':True,'deterministic_fallback':False,'public_gate_status':'PASS','source_origin':'local'}).passed)"

# Freeze
python3 -c "from nexus.services.local_heal.evidence_freeze import build_freeze_report; print(build_freeze_report('.').summary())"
```
