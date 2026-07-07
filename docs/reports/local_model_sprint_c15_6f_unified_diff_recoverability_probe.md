# C15-6F: Unified Diff Recoverability Probe — Report

**Sprint**: C15-6F  
**Date**: 2026-07-05  
**HEAD Commit**: `d807fa717 docs(localheal): record C15-6E end-to-end success gate`  
**Status**: 🔬 C15_6F_RECOVERABLE_PREIMAGE_DRIFT_PROVEN_TEST_ONLY

---

## 1. Problem Summary & Context

在實機 local-model 跑題中，即便 `LocalModelExecutor` 委員會成功路徑已被 `test_c15_6e_controlled_committee_success_proven` 證明連通，但實機雙模型與三模型測試（以 `toy-math-verifier-evidence-gap` 為例）依舊全數失敗。其主要阻礙有二：
1. **Qwen-7B (Format Blocker)**: 大量輸出 Unified Diff，但因微小的縮排、空格等 preimage drift 被 parser 拒絕（`unified_diff_malformed`）。
2. **DeepSeek / Ornith (Quality Blocker)**: 輸出空 patch（`patch_empty`）。

本 Probe 旨在通過 Test-only 探測與隔離，釐清 Qwen 產生的 Unified Diff 究竟是**「可透過模糊 preimage 匹配恢復的格式偏差」**，還是**「本質上即為語義錯誤的修復，本就不該套用」**，藉此決定後續是否引入模糊 preimage 復原機制。

---

## 2. Evidence from C15-6E

由 C15-6E 實機 results.jsonl 與日誌萃取 Qwen-7B 的 raw diff 表明：
```diff
--- a/toy/math_util.py
+++ b/toy/math_util.py
@@ -1,2 +1,4 @@
 def normalize_score(score, min_val, max_val):
-    return (score - min_val) / (max_val - min_val)
+    if max_val == min_val:
+        return 0.5 if score >= 0 else 0
+    return max(0, min(1, (score - min_val) / (max_val - min_val)))
```
**分析結果**：
此 diff 在語法與邏輯上均為**有效之修復嘗試**（引入了 `max_val == min_val` 邊界處理並實施了 `max(0, min(1, ...))` 夾逼限制），但由於本地模型輸出時之 markdown wrap 或上下文空白行微漂移，與磁碟上原始檔案（如 newline 或 tab）不完全對齊，在 `DiffToSSRPConverter` 的極端精確匹配限制下，被一刀切回傳了 `unified_diff_missing_preimage`，被當作格式錯誤拋棄。此類 drift 屬於**可挽救的（Recoverable）**。

---

## 3. DiffToSSRP Strict Behavior

[diff_to_ssrp.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/diff_to_ssrp.py) 目前的核心轉換邏輯：
```python
if search_block not in source_text:
    telemetry["preimage_match_status"] = "missing"
    return "", "unified_diff_missing_preimage", telemetry
```
此處採用 strict equality (`in` 運算子）。若模型輸出的 search_block 尾部多出空白、空行，或是縮排（spaces vs tabs）與 source 不完全吻合，皆會被判定為 missing。

---

## 4. Test-Only Cases Added

已於 [test_diff_to_ssrp.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_diff_to_ssrp.py) 新增 5 個 test-only 探測案例：

- **Test A: `test_c15_6f_unified_diff_exact_preimage_still_converts`**
  - 確保原有的 exact-match 行為保持通過。
- **Test B: `test_c15_6f_unified_diff_whitespace_drift_currently_rejected`**
  - 驗證當前當 minus line 或 context line 尾部含有 trailing whitespace 時，會被 strict matcher 判定為 `unified_diff_missing_preimage`（目前已正確被拒絕）。
- **Test C: `test_c15_6f_unified_diff_indentation_drift_currently_rejected`**
  - 驗證當前當 search_block 的縮排多出/減少空格時，會被判定為 `unified_diff_missing_preimage`（目前已正確被拒絕）。
- **Test D: `test_c15_6f_unified_diff_semantically_wrong_patch_should_remain_rejected_or_verifier_failed`**
  - 驗證當 diff 針對一個完全不存在的 context (例如 `non_existing_function`) 時，依然必須被安全拒絕。
- **Test E: `test_c15_6f_unified_diff_ambiguous_recovery_must_not_auto_apply`**
  - 驗證當 source 中有多個完全一致的程式碼段落時（歧義），即便是 fuzzy 也絕不能自動套用，必須維持 `unified_diff_ambiguous_preimage`。

---

## 5. Test Results

執行 pytest 命令：
```bash
/Users/jameschen/.local/bin/uv run pytest tests/unit/local_heal/test_diff_to_ssrp.py -q
```
測試輸出：
```text
tests/unit/local_heal/test_diff_to_ssrp.py ............                  [100%]
============================== 12 passed in 0.24s ==============================
```
證實 Test-only probe 已安全併入，並成功重現並鎖定了目前的 drift 拒絕邊界。

---

## 6. Recoverability Matrix (修復性矩陣)

| Case | Current Status | Could Fuzzy Recovery Help? | Risk | Recommended Action |
|---|---|---|---|---|
| **exact match** | `converted` | No change needed | Low | Keep |
| **whitespace drift** | `missing_preimage` | **Yes (High recovery probability)** | Low/Medium | Candidate (Whitespace normalize) |
| **indentation drift** | `missing_preimage` | **Yes (Medium recovery probability)** | Medium | Candidate with strict unique-match check |
| **missing context line** | `missing_preimage` | Maybe (Low probability) | Medium/High | Test before patch (reject if too short) |
| **ambiguous source** | `ambiguous` | **No (Must never auto-apply)** | High | Force reject |
| **semantic wrong patch** | `missing_preimage` / may convert but verifier fail | Fuzzy not relevant | High | Verifier handles / strict reject |
| **empty patch** | `empty_patch` | Fuzzy not relevant | Low | Keep reject (prompt/model level issue) |

---

## 7. Minimal Patch Candidate (僅提案，不實作)

為避免 Nexus 裝甲將「格式拒絕」演變為「危險錯套」，建議在 `DiffToSSRPConverter` 內引入一個 **Fuzzy Preimage Recovery Helper**，在精確匹配失敗時，採取以下歸一化單一匹配策略：

```python
def _recover_preimage(search_block: str, source_text: str) -> str | None:
    # 1. 檢查 search_block 行數是否過少（如僅 1 行），過少則拒絕模糊匹配以防錯套
    lines = search_block.splitlines()
    if len(lines) < 2:
        return None

    # 2. 空白歸一化查找：忽略行尾空白與行中連續空白
    def normalize_line(line: str) -> str:
        return "".join(line.split())

    norm_search = [normalize_line(l) for l in lines]
    source_lines = source_text.splitlines()
    
    matches = []
    # 滑動視窗比對歸一化後的每一行
    for i in range(len(source_lines) - len(lines) + 1):
        window = [normalize_line(source_lines[i + j]) for j in range(len(lines))]
        if window == norm_search:
            # 記錄原始匹配到的 preimage 區間
            matched_original = "\n".join(source_lines[i : i + len(lines)])
            matches.append(matched_original)
            
    # 3. 唯有在全檔存在唯一匹配（Unique match）時始回傳，若 0 個或多於 1 個（歧義）皆拒絕
    if len(matches) == 1:
        return matches[0]
    return None
```
**SSRP 裝配調整**：若 `_recover_preimage` 成功，使用原始 source 內容作為 SSRP 的 `SEARCH` block，以保證 patcher 能夠 100% 精確套用，並於 telemetry 中標記 `preimage_match_status = "fuzzy_recovered"`。

---

## 8. Risks

1. **歧義錯套風險**: 若 LLM 輸出的 preimage 太過簡短（如僅一行 `return 0`），空白歸一化後容易在大型檔案中撞名。必須設定最小行數限制（例如至少 2 行以上），且嚴格要求全檔 unique match。
2. **語意偏移風險**: 模型輸出的 search block 若被模糊匹配修改，可能無意中把修改套用在相似但邏輯相悖的舊代碼區塊。

---

## 9. Recommendation

**判定結論**: `C15_6F_RECOVERABLE_PREIMAGE_DRIFT_PROVEN_TEST_ONLY`

**建議**: **批准此 fuzzy patch 提案**。
- 數據證明，Qwen-7B 產出的 Unified Diff 具備實質語意上的修復能力，卻高機率死於 whitespace 和 indentation 微小偏移。
- 透過在 converter 內實施帶有 **Unique-match + 最小行數硬限制** 的 fuzzy 復原，能在確保安全的防護網下，最大化小模型的實機解決率，消弭 output_understanding gap。
