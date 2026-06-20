---
type: ADR
status: accepted
tags: [nexus, ADR, evolution, patch-protocol, ast-rewriter]
---

# ADR-2026-06-19: 降級 SEARCH/REPLACE 協議並引入 AST-guided line-span 重寫器與 Abbreviated Traceback 機制

## Status
Accepted

## Context
在本地資源受限環境（16GB RAM）下，我們觀測到本地小模型（7B, 14B Q3）在執行 Aider 的 verbatim `SEARCH/REPLACE` 協議時面臨極高的失敗率（`SEARCH_MISMATCH` 失敗率達 100%）。主要痛點如下：
1. **Verbatim 匹配脆弱性**：小模型難以 100% 精確複製多行原始代碼。微小的縮進、換行符、或是空白字元差異均會觸發 `SEARCH_MISMATCH`，甚至導致 closest_match 算法尋找到錯誤的程式碼區間進行錯誤修改。
2. **Context Budget 與量化折衷**：14B 模型使用 `q3_K_M` 量化勉強在 8192 tokens 下推論，但量化失真嚴重，推論能力嚴重退化，無法穩定輸出符合格式 of verbatim 替換區塊；若退回 7B 高精度模型，則受限於 context window 太窄，無法讀入整個原始檔案。
3. **Traceback 噪音干擾**：單次失敗重試（verifier-guided retry）時，Python 完整的 unittest traceback 非常冗長，擠佔了本就珍貴的 Context window，導致後續重試的品質急劇下降。
4. **3B Advisor 效能卡點**： deterministic S2TSelector 精確度達 100% 後，3B Advisor 的 override 作用被壓縮至 0.0%，面臨嚴重的 Ceiling Effect，亟需角色轉型。

## Decision
我們正式決定將 `SEARCH/REPLACE` 協議降級為 fallback/audit 協議，並將 Primary Patch Protocol 重構為 **AST-guided rewriter + line-span patch + source hash guard** 三維防護體系。同時實施 TSP (Task-Specific Partitioning) 固定分工，並在驗收與重試環節硬化 traceback 精簡與主動放棄（abstention）機制。

### 1. 新 Patch Schema 設計
新協議取消模型逐字複製原代碼的要求，改為模型輸出 target 定位特徵與 replacement 代碼，由 Nexus 引擎負責 AST 定位與 patch 套用。

```json
{
  "file_path": "astropy/modeling/separable.py",
  "source_hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
  "targets": [
    {
      "type": "function",
      "class_name": null,
      "name": "is_separable",
      "line_span": [120, 135],
      "intent": "fix separable validation logic for compound models",
      "replacement": "    # 新的實作代碼，由 Nexus 引擎定位至該行區間進行安全套用\n    return _separable(transform)"
    }
  ]
}
```
* **AST-guided rewriter**：定位器使用 Python/Rust 語法解析器，根據 class_name、name 與 type 鎖定 AST 節點，驗證模型修改範圍是否限制在目標 symbol 內部，拒絕任意代碼注入。
* **Line-span patch**：結合行號範圍 `line_span` 定位，避免因字面微小差異匹配失敗。
* **Source hash guard**：檔案在 localization 階段與 patch 生成階段皆進行 SHA-256 哈希校驗，若檔案被其他 swarm worker 併發修改導致哈希不一致，則拒絕套用（回報 `source_stale`），防範 State Drift。

### 2. Verifier-Guided Retry 與 Abbreviated Traceback 格式
重試迴圈（retry loop）中，Nexus 負責在餵給小模型前將 python 錯誤簡化為 **Abbreviated Traceback**，限制在 300 tokens 以內：
```text
[ERROR_TYPE]: AssertionError
[MESSAGE]: 'CompoundModel' object has no attribute 'separable'
[MINIMIZED_STACK]:
  - file: astropy/modeling/separable.py, line 125, in is_separable
  - file: astropy/tests/test_separable.py, line 45, in test_compound_separable
[TARGET_LINES]:
  124:     else:
  125:         return transform.separable
  126: 
[ASSERT_DIFF]:
  - expected: True
  + actual: False
[RECENT_PATCH_DIFF]:
  @@ -125,1 +125,1 @@
  - return transform.separable
  + return _separable(transform)
[VERDICT]: FAILED (verifier verdict: attribute_error)
```

### 3. TSP (Task-Specific Partitioning) 新角色分工
* **7B 模型 (Localizer & Repro Builder)**：負責輕量長上下文。執行代碼檢索、精確定位（Localization，找出 Class/Method 範圍並提供 symbol 級 crop），並建構 bug 重現腳本。
* **14B 模型 (Patch Synthesizer - Q8/FP16 窄上下文)**：專注於窄上下文的 patch 合成。不再讀取整檔，僅讀取 7B 裁剪後的 context（控制在 2048 tokens 以內），從而能使用高精度的 Q8/FP16 量化，避免 Q3 推論能力退化。
* **3B 模型 (Retriever, Scorer & Failure Classifier)**：轉型為 Slice Scorer（評估代碼切片相關性分數）、Failure Classifier（ traceback 錯誤分類）以及 Abstention Predictor（主動放棄預判）。

### 4. Runtime Abstention Gate 硬化
在超預算、低 source anchor 匹配率、低 span confidence、或是 verifier持續無改善時，引入 Rule-based Validator 在推理出口強行截斷，直接返回 `FAILED`、`ESCALATED` 或 `HUMAN_REVIEW`，硬化本地模型的主動放棄能力（Abstention），不再盲目跟隨 baseline。

## Migration Plan
1. **Phase 1: Traceback Compression**：在 Runner 引入 `AbbreviatedTracebackFormatter`，壓縮 traceback 噪訊。
2. **Phase 2: Parser & Guard Implementation**：實作 `ASTLocator` 與 `SourceHashGuard` 機制，支援讀取新 Patch JSON Schema。
3. **Phase 3: Route Transition**：將 primary patch protocol 切換為新 schema，並將舊的 SEARCH/REPLACE 降級為 fallback/audit 格式。
4. **Phase 4: Run A/B Benchmarks**：使用 swebench_lite 的 astropy/sympy 任務包驗證新舊 protocol 效能。

## Minimal Verification Test
* **Test 1: Hash Guard Rejection**
  - 當檔案被手動修改（導致哈希不一致）時，`SourceHashGuard` 必須成功偵測並報出 `source_stale`。
* **Test 2: AST Node Positioning & Patch Application**
  - 在有空白/縮進微小差異的原始檔中，`ASTLocator` 應能準確定點到 `is_separable` 函數，套用 line-span patch，且此操作在 `SEARCH_MISMATCH` 基準測試下應為 100% 成功。
* **Test 3: Abbreviated Traceback Token Budget**
  - 輸入 2000 字元的完整 stack trace，經過簡化後應小於 300 tokens，且保留 filename、line 與 assert diff 關鍵欄位。
* **Test 4: TSP E2E Integration Flow**
  - 模擬 7B 定位 -> 14B Q8 生成 patch -> 3B 驗證流程，確保資料鏈路完整且無 context 溢出現象。
