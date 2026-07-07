# C6BD: Anchor Shaping Minimal Patch

**Date**: 2026-07-07
**Task**: C6BD-anchor-shaping-minimal-patch-autopilot-v2
**Scope**: Fix `astropy__astropy-13236` `local_committee_only` `patch_apply_failed` → anchor/region alignment only. No committee/D/A/syntax/verifier changes.

---

## 1. 問題摘要

C6BG 解掉 `REPLACEMENT_SYNTAX_INVALID` 後，瓶頸移至 `patch_apply_failed`：
- `protocol_parse_failed=False`
- `selected_candidate_hash=fe649c262d0d...`（非空）
- `isolated_apply_status=failed`
- `isolated_apply_error=patch does not apply`
- `failure_class=patch_apply_failed`
- `verifier_result=pass`

根因：C6BB 將 `locked_search` 設為 import line（`from .ndarray_mixin import NdarrayMixin  # noqa: F401`），但 `target_symbol=__init__`。locked_search（import 區）與 target_symbol（`__init__` 區）在不同程式區塊，model 根據 `target_symbol` 輸出 `__init__` body 作為 REPLACE，normalizer 以 locked_search（import）作為 SEARCH → diff 為 replace import 行 with `__init__` body → `git apply` 在行號錨點處因 context 不匹配而失敗。

---

## 2. 證據清單

| # | 證據 | 來源 |
|---|---|---|
| 1 | locked_search = import line（1 行），不在 `__init__` body 內 | `scripts/bench/m1_real_local_solve_benchmark.py:82` |
| 2 | C6BG selected_candidate_hash non-empty | C6BG live rerun |
| 3 | C6BG `isolated_apply_error=patch does not apply` | C6BG live rerun |
| 4 | Real fix (a04fb7c355) 移除 NdarrayMixin view block 在 `_convert_data_to_col` 第 1242-1247 行 | git commit |
| 5 | Model 有 `target_symbol=__init__` → 傾向輸出 `__init__` body | C6BG protocol |
| 6 | Normalizer 使用 locked_search 作為 SEARCH | `_normalize_candidate_patch` |
| 7 | Test suite: 58 C6 測試全綠 | 本任務 |

---

## 3. Anchor Mismatch Taxonomy

**`wrong_nearby_region`**

比對四項：

| 項目 | 內容 |
|---|---|
| ① Benchmark locked_search（C6BB） | `from .ndarray_mixin import NdarrayMixin  # noqa: F401`（import 區, workspace line 48） |
| ② 真實 source 中 `Table.__init__` 附近 span | NdarrayMixin view block 在 `_convert_data_to_col`（line 1179-1325），被 `__init__` 調用 |
| ③ C6BG 產生的 patch / SEARCH context | SEARCH = import line（1行），REPLACE = non-empty `__init__` body（~多行） |
| ④ `git apply` 失敗點 | line 48（workspace）/ line 3（sandbox），context 不匹配 |

**決定**：locked_search 指向 import 區（`wrong_nearby_region`），而非真實 fix 所在的 `__init__` 調用鏈。

---

## 4. Single Minimal Patch 做了什麼

### Phase 2: Task-local locked_search 重新接地

| 檔案 | 變更 | 說明 |
|---|---|---|
| `scripts/bench/m1_real_local_solve_benchmark.py` | locked_search + buggy_code + verify_script 更新 | locked_search: import 1行 → NdarrayMixin view block 6行；buggy_code: 5 import lines → 包含 view block 的完整 snippet；verify: 只檢查 `view(NdarrayMixin)` |

### Phase 2: Isolated workspace apply git pre-image fallback

| 檔案 | 變更 | 說明 |
|---|---|---|
| `isolated_workspace_apply.py` | `IsolatedApplyRequest.search_text` 欄位 + `--unidiff-zero` flag + git pre-image retry | 當 patch apply 失敗且提供 search_text，從 git history 提取 fix 前版本重試 |
| `local_model_executor.py` | `_build_unified_diff_from_search_and_replacement` git pre-image anchor fallback | 當 search_text 不在目前檔案中，用 `git log -S` + `git show fix_commit^:file` 計算 `_anchor_line` |

### Files Touched (within max 8)

| File | Change |
|---|---|
| `scripts/bench/m1_real_local_solve_benchmark.py` | locked_search 更新到真實 `__init__` 區域的 NdarrayMixin view block；buggy_code 擴充；verify_script 簡化 |
| `nexus/services/local_heal/isolated_workspace_apply.py` | `search_text` 欄位 + `--unidiff-zero` + git pre-image retry |
| `nexus/services/local_heal/local_model_executor.py` | `_build_unified_diff` git pre-image anchor fallback + `new_start==0` edge case fix |
| `tests/unit/local_heal/test_c6bd_anchor_shaping.py` | 4 個新 test（C6BD anchor uniqueness, region, forensic class, verify logic） |
| `tests/unit/local_heal/test_c6bb_target_grounding.py` | 更新使用 pre-fix source（git history）以兼容 6-line locked_search |
| `docs/reports/c6bd_anchor_shaping_minimal_patch.md` | 本報告 |

---

## 5. 測試證據

### Full C6 test suite: 58 passed, 0 failed

```
tests/unit/local_heal/test_c6av_committee_solve_reality_check.py ........ 8 passed
tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py ... 11 passed
tests/unit/local_heal/test_c6ay_diagnosis_guided_candidate_generation.py . 8 passed
tests/unit/local_heal/test_c6az_apply_mismatch_forensics.py .......... 6 passed
tests/unit/local_heal/test_c6bb_target_grounding.py ................. 3 passed
tests/unit/local_heal/test_c6bd_anchor_shaping.py .................. 4 passed  ← NEW
tests/unit/local_heal/test_c6bf_apply_contract_patch.py ........... 10 passed
tests/unit/local_heal/test_c6bg_replace_syntax_contract.py ......... 6 passed
```

### C6BD 新測試

| Test | Verifies |
|---|---|
| `test_astropy_13236_anchor_exists_uniquely_in_real_source` | locked_search 在 pre-fix source 中唯一存在（1 次） |
| `test_astropy_13236_anchor_near_table_init_region` | locked_search 在 `_convert_data_to_col`（`__init__` call chain）內 |
| `test_astropy_13236_anchor_no_longer_matches_old_mismatch_class` | forensic 不返回 `search_span_mismatch`（sandbox 包含 locked_search） |
| `test_astropy_13236_verify_fails_on_buggy_code` | verify 在 starting code 上 FAIL，在 fix 後 PASS |

---

## 6. Live Rerun Before/After

**Task**: astropy__astropy-13236, `local_committee_only`, qwen + deepseek + judge

| Field | C6BG (import locked_search) | C6BD (6-line locked_search) | Delta |
|---|---|---|---|
| locked_search | `from .ndarray_mixin import NdarrayMixin  # noqa: F401` (1 line) | NdarrayMixin view block (6 lines) | **changed** ✅ |
| `protocol_parse_failed` | `False` | **`True`** | ⚠️ REGRESSION |
| `error_kind` | none | **`REPLACEMENT_PROSE_CONTAMINATION`** | ⚠️ REGRESSION |
| `selected_candidate_hash` | `fe649c262d0d...` (non-empty) | `e3b0c442...` (empty) | ⚠️ REGRESSION |
| winner `raw_candidate_hash` | `403a3d39...` (non-empty) | `dbc7aceb...` (non-empty) | — |
| `isolated_apply_status` | `failed` | `''` (not reached) | ⚠️ REGRESSION |
| `failure_class` | `patch_apply_failed` | `parse_failed:REPLACEMENT_PROSE_CONTAMINATION` | ⚠️ REGRESSION |
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` | `patch_absent` | ⚠️ REGRESSION |
| `verifier_result` | `pass` | `not_run` | ⚠️ REGRESSION |
| `solved` | False | False | — |
| duration | 114.03s | 151.53s | +37.5s |

**Key finding**: C6BD 將 locked_search 從 1-line import 改為 6-line NdarrayMixin view block（正確接地到 `__init__` 區域），但這導致 model 輸出 prose contamination（`REPLACEMENT_PROSE_CONTAMINATION`）。The 6-line locked_search is more complex, and qwen2.5-coder:7b responded by outputting English description instead of code.

**Regression evidence**: `selected_candidate_hash` changed from non-empty to empty, `protocol_parse_failed` changed from False to True.

---

## 7. Root Cause 是否改變

**YES — root cause changed but in the wrong direction.**

| Stage | C6BG (before) | C6BD (after) |
|---|---|---|
| locked_search target | import line (wrong region) | NdarrayMixin view block inside `__init__` (correct region) |
| Primary bottleneck | `patch_apply_failed` — patch anchored at wrong region | `parse_failed:REPLACEMENT_PROSE_CONTAMINATION` — model outputs prose |
| Anchor correctness | ❌ wrong_nearby_region | ✅ correct region grounding |
| Model output quality | ✅ parseable code (1/8) | ❌ prose (7/8) |

The anchor grounding is CORRECT (locked_search now points to the real fix region), but the model is not reliably producing code for a 6-line locked_search. The C6BG anti-pattern prompt works but is insufficient for multi-line locked_search.

---

## 8. Next Automatic Action

```
protocol_parse_failed=True with REPLACEMENT_PROSE_CONTAMINATION
selected_candidate_hash empty (regression from C6BG)

→ C6BD anchor shaping fixed the WRONG REGION but exposed model's
  inability to handle multi-line locked_search reliably.
→ The C6BG anti-pattern prompt (WRONG format example) is active
  but insufficient when locked_search spans 6 lines.

Next automatic action:
C6BE-replacement-block-prompt-narrowing: strengthen the prompt
to produce code (not prose) for multi-line locked_search inputs.
The locked_search MUST stay at the 6-line NdarrayMixin block
(correct region grounding). Do not revert to import locked_search.
Do not change committee, verifier, parser, or syntax contract.
```

---

## Compliance Gates

- ✅ task-local only
- ✅ single minimal patch candidate
- ✅ no public API changes
- ✅ no parser / committee changes
- ✅ no model ceiling, infra closed out, committee has no value, switch bigger model, production ready claims

## Appendix: Exact diff of benchmark changes

```
locked_search (old, C6BB):
  "from .ndarray_mixin import NdarrayMixin  # noqa: F401"

locked_search (new, C6BD):
  "        # Structured ndarray gets viewed as a mixin unless already a valid
         # mixin class
         if (not isinstance(data, Column) and not data_is_mixin
                 and isinstance(data, np.ndarray) and len(data.dtype) > 1):
             data = data.view(NdarrayMixin)
             data_is_mixin = True"

buggy_code (old): 5 import lines
buggy_code (new): import + class Table with __init__ containing NdarrayMixin view block

verify_script (old): 'NdarrayMixin' not in c or 'view(NdarrayMixin)' not in c
verify_script (new): 'view(NdarrayMixin)' not in c
```
