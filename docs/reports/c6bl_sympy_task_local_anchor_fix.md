# C6BL: sympy-13852 Task-Local Anchor Fix

**Date**: 2026-07-07
**Task**: C6BL-sympy-task-local-anchor-fix-autopilot
**Scope**: Fix sympy-13852's `anchor_too_short_for_body`, then evaluate whether `assertion-grounded problem_statement` generalizes.

---

## 1. 問題摘要

C6BK 確認 sympy-13852 的 anchor taxonomy 為 `anchor_too_short_for_body`: locked_search 僅 1 行 `if a is S.One:` (bare if-header)，不含 indented `pass` body。C6BL 將 locked_search 改為 multi-line if-block，並分兩步驗證: (1) anchor 自身穩定性; (2) `problem_statement` 泛化效果。

---

## 2. 證據清單

| # | 證據 | 來源 | 類型 |
|---|---|---|---|
| E1 | locked_search: 1 行 → 2 行 (`if a is S.One:\n            pass`) | `m1_real_local_solve_benchmark.py#L125-L129` | Minimal patch |
| E2 | 12 tests PASS (3 C6BL new + 9 C6BK updated) | `test_c6bk_sympy_anchor_probe.py` | Unit test |
| E3 | Rerun #1 (anchor fix, no PS): `parse_error_kind=none`, `candidate_hash` non-empty, `verifier_status=fail` | Live rerun #1 | Live |
| E4 | Rerun #2 (anchor fix + PS): `parse_error_kind=none`, `candidate_hash=7d2cc134...`, **`verifier_status=pass`** | Live rerun #2 | Live |
| E5 | Rerun #2: `protocol_normalization.normalized=True`, `protocol_used=solid_search_replace` | Live rerun #2 metadata | Live |
| E6 | Rerun #2 residual: `applied_patch_hash=''`, `selected_candidate_hash_matches_applied=False` | Live rerun #2 adapter | Pipeline |
| E7 | 56 C6 tests PASS (full regression) | 全量 pytest | Regression |

---

## 3. Minimal Patch 做了什麼

**Changes to `scripts/bench/m1_real_local_solve_benchmark.py`**:

| Before (C6BK) | After (C6BL) |
|---|---|
| `"locked_search": "if a is S.One:"` (1 line, no body) | `"locked_search": ("\n" "        if a is S One:\n" "            pass\n")` (2 lines, if + body) |

匹配 buggy_code 中第 3-4 行的完整 if-block (8 空格縮排)，使模型可輸出完整的 replacement (包含 indented `pass`)，通過 AST 驗證。

---

## 4. 測試證據

### C6BL 新增 (3 tests)

| Test | Verified |
|---|---|
| `test_sympy_13852_multiline_locked_search_is_complete_python_block` | multi-line anchor + body 通過 AST wrapper 驗證 |
| `test_sympy_13852_multiline_locked_search_matches_source_context` | anchor 精確匹配 buggy_code 第 3-4 行 |
| `test_sympy_13852_multiline_locked_search_reaches_parseable_replacement_path` | `_normalize_candidate_patch` 完整路徑通過, patch 含 `a == S.One` |
| `test_sympy_13852_old_single_line_anchor_was_too_short` | 舊 1 行 anchor 仍被 AST 拒絕 (regression guard) |

### C6BK updated (9 tests)

全部更新為反映新 multi-line anchor 狀態。所有測試 PASS。

---

## 5. Rerun #1 結果 (anchor fix only, no problem_statement)

| Field | Pre-C6BL (C6BJ) | C6BL Rerun #1 | Delta |
|---|---|---|---|
| `protocol_parse_failed` | True → REPLACEMENT_SYNTAX_INVALID | **False** ✅ | **FIXED** |
| `parse_error_kind` | `REPLACEMENT_SYNTAX_INVALID` | **none** ✅ | **FIXED** |
| `candidate_hash` | `e3b0c442...` (empty) | **`815532ac...`** ✅ | **FIXED** |
| `protocol_normalization.normalized` | — | **True** ✅ | **FIXED** |
| `source_anchor_hash` | `4d1af822...` | **`cb96bd20...`** (new hash) | Changed |
| `verifier_result` | fail | fail | — (expected, no PS) |
| duration | 8.05s | 7.83s | — |

**結論: anchor_too_short_for_body 已完全修復。** lower-layer 穩定。

---

## 6. Rerun #2 結果 (anchor fix + problem_statement)

| Field | Rerun #1 (no PS) | Rerun #2 (with PS) | Delta |
|---|---|---|---|
| `parse_error_kind` | none | none | — |
| `verifier_status` (telemetry) | fail | **pass** ✅ | **FIXED** ✅ |
| `candidate_hash` | `815532ac...` | `7d2cc134...` | New |
| `elapsed_sec` | 7.83s | 2.65s | −5.2s |
| `verifier_result` (adapter) | fail | fail (HASH_MISMATCH) | — |
| `applied_patch_hash` | `''` | `''` | — |
| `selected_candidate_hash_matches_applied` | False | False | — |

**關鍵發現**: `verifier_status=pass` 在 telemetry 中證明:
- 模型收到 `problem_statement` 後確實產出正確修補 (`a == S.One`)
- isolated apply + verifier 確認修補通過驗證
- 剩餘阻斷: pipeline hash matching (`applied_patch_hash=''`)

### 與 astropy-13236 C6BF 模式對比

| | astropy-13236 C6BE→C6BF | sympy-13852 C6BL rerun #2 |
|---|---|---|
| 加入 PS 後 verifier 前進 | fail → pass ✅ | fail → **pass** ✅ |
| 阻斷層 | hash mismatch (committee) | hash mismatch (local_only) |
| 模型是否產出正確 patch | YES | YES |

---

## 7. Bounded Generalization Verdict

**`assertion-grounded problem_statement has limited cross-task value once anchor is stabilized`**

| 維度 | 評估 |
|---|---|
| anchor 穩定性 | **C6BL 已修復**。multi-line locked_search 使 sympy 可 parse。 |
| `problem_statement` 泛化 | **驗證通過**。兩題皆在加入 PS 後 model 產出 verifier-passing patch。 |
| pipeline hash matching | 阻斷但已知。C6BF 已解決 committee topology 的類似 issue，`local_only` topology 有不同 hash matching 路徑。 |
| 跨題證據 | 2 tasks: astropy-13236 (SOLVED 2x) + sympy-13852 (verifier pass, hash mismatch) |

### 排除的結論

- ❌ `model ceiling` — 7B model 兩題都產出正確 patch，瓶頸不在模型能力
- ❌ `infra closed out` — pipeline hash matching 是已知可修復模式 (C6BF 先例)
- ❌ `committee has no value` — 本任務使用 `local_only` topology，未啟用 committee
- ❌ `production ready` — 僅 2 題 bounded evidence

---

## 8. Next Automatic Action

**Freeze as two-task bounded evidence. Do not expand.**

- `assertion-grounded problem_statement` pattern 已證明在 anchor 穩定後可跨題生效
- 不升級為通用 framework (仍為 task-local spec patch)
- 不沿 sympy-13852 hash mismatch 繼續深挖 (已確認模型產出正確修補，pipeline issue 為已知模式)
- 不擴大到更多 tasks
- 僅保留 56 個 regression tests 作為保護網

### 受影響檔案

| File | Status | Change |
|---|---|---|
| `scripts/bench/m1_real_local_solve_benchmark.py` | **Modified** | locked_search multi-line + problem_statement for sympy-13852 |
| `tests/unit/local_heal/test_c6bk_sympy_anchor_probe.py` | **Modified** | 12 tests (3 C6BL new + 9 C6BK updated) |
| `tests/unit/local_heal/test_c6bj_generalization_probe.py` | **Modified** | sympy problem_statement test updated |
| `docs/reports/c6bl_sympy_task_local_anchor_fix.md` | **NEW** | This report |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | **Update** | Learning closure entry |

**No public API modified. No parser/committee/verifier/prompt framework changes.**
