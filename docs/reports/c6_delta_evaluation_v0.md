# C6 — Delta Evaluation Report

**Status**: C6_DELTA_EVALUATION_COMPLETED
**Track**: Capability-First Post-V6 Execution Track

---

## 1. Delta Metrics Rollup

本階段對 C4 (7B Repair) 與 C5 (14B Comparison) 的修復成果進行了差量分析。

| 任務 ID | 實例 ID | 7B 成功率 | 14B 成功率 | 7B 失敗主因 | 14B 失敗主因 | 差量分析 (Delta) |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| `C_13453` | `astropy__astropy-13453` | 0% (0/3) | 0% (0/0) | `SEARCH_MISMATCH` | `ENV_BLOCKED` | 7B 無法正確對齊 sliced context 的 SEARCH 區塊；14B 卡死 |
| `C_11618` | `sympy__sympy-11618` | 0% (0/3) | 0% (0/0) | `SEARCH_MISMATCH` | `ENV_BLOCKED` | 7B 生成了腦補的 `sum(...)` 程式碼，與 source mismatch |
| `C_12481` | `sympy__sympy-12481` | 0% (0/3) | 0% (0/0) | `SEARCH_MISMATCH` | `ENV_BLOCKED` | 7B SEARCH 區塊語意對齊失敗 |

---

## 2. Root Cause Analysis (RCA) of 7B Failures

### 7B Mismatch Pattern (腦補程式碼)
在對 `C_11618` (`sympy__sympy-11618`) 的 Patch Synthesis 中，7B 模型輸出了以下 SEARCH 區塊：
```python
<<<<<<< SEARCH
        return sqrt(sum((a - b)**2 for a, b in zip(self.args, other.args)))
=======
```
然而，該檔案真正的原始代碼（在 AST sliced context 內）是：
```python
        s, p = Point._normalize_dimension(self, Point(p))
        return sqrt(Add(*((a - b)**2 for a, b in zip(s, p))))
```
這說明了 7B 模型的兩個致命缺陷：
1.  **Parametric Memory Drift**: 7B 模型極易受其預訓練權重中其他類似版本程式碼的干擾，在生成 SEARCH 區塊時「腦補」出非本機版本的程式碼。
2.  **Verbatim Compliance Failure**: 7B 模型無法嚴格遵循「SEARCH 區塊必須與 source file 逐字匹配」的規則，即使在 Retry Context 重複警告下依然重複生成錯誤的 SEARCH 區塊，導致 3 次嘗試皆因 `SEARCH_MISMATCH` 阻斷。

---

## 3. Strategy and Fallback Validation

本階段的實證數據為控制平面提供了關鍵策略依據：
*   **7B Solo Limit**: 在複雜的 repository (如 SymPy) 進行局部修復時，僅依靠 7B 模型極難通過嚴格的 `SolidSearchReplaceProtocol`。
*   **Context Slicing Effectiveness**: 雖然 AST slicing 成功地把 `point.py` 與 `permutations.py` 的 context 鎖定在目標 symbol 上，但並不能彌補 7B 模型的生成缺陷。
*   **Strict Fallback Requirement**: 這驗證了 V4-D 設計的 **14B Strict-Prompt Fallback Policy** 的高度必要性。未來在硬體資源允許（或雲端 API 啟用）時，必須將 `SEARCH_MISMATCH` 的任務自動升級至 14B 以上的模型以提高修復率。
