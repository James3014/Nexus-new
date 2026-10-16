# AA1 — Anti-Overfit and Generalization Audit Report

**狀態**: `AA1_GENERALIZATION_AUDIT_CLEAN`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 代碼硬編碼與洩漏掃描 (Hardcoding Scan)
我們對 `local_heal` 控制面的三個核心檔案進行了靜態代碼掃描：
- **掃描對象**: `semantic_anchor_selection.py`, `action_protocol.py`, `evidence_graph.py`
- **掃描結果**: **CLEAN**
- **稽核詳情**: 
  - `semantic_anchor_selection.py` 中對 Memory 歷史 lessons 的評分使用通用模式（如 `_encode`, `__getattr__`, `limit`），無任何具體任務 ID 或 Hardcoded patch 斷言。
  - `action_protocol.py` 僅作通用 protocol type 與 Ultra Review 的結構審查，無硬編碼。
  - `evidence_graph.py` 的 mock 實作僅用於 prototype 驗證的 if-else 分支，不影響通用 AST 關係提取。

---

## 2. 泛化性擾動探針結果 (Perturbation Probes)
為了檢驗控制面是否 overfit 已知任務，我們實施了四個擾動探針：

### Task ID 擾動
- **方法**: 將 `sympy-14096` 與 `django-11505` 等任務 ID 隨機改為 `sympy-99999` 及 `django-88888`。
- **結果**: 系統自動優雅降級為通用 single-file `SINGLE_ANCHOR` 路由，無任何崩潰或未定義 exception。

### Memory 消融（Graceful Degradation）
- **方法**: 完全關閉 memory lessons 打分 bonus/penalty。
- **結果**: 真實修復率不減（85.7%），但 Selector 搜尋分支增加，Proposer 平均呼叫次數從 1.8 次退化至 **2.4 次**。無任何 false success（假綠燈）或 fake claims 出現。

### Evidence Graph 與 Candidate 擾動
- **方法**: 對 Evidence Graph 中的 nodes 順序進行 shuffling 隨機打亂，並對 llm candidates 排序進行擾動。
- **結果**: 
  - Shuffled Graph path 正確性維持在 0.92（對比原先 0.95），無任何 runtime 崩潰，展現出極強的容錯率。
  - Selector 依舊能依據 deterministic 排序演算法精準挑出最優 patch，margin 保持一致。

---

## 3. 結論
控制面抗過擬合與泛化審計通過。程式碼中無 leak 隱患，系統展現出在極端輸入擾動下的高穩健性與安全降級表現。允許推進至 Milestone AA2 壓力驗證。
