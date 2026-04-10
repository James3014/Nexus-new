# 🛡️ Nexus v24.1: Credible Optimization Protocol (可信最佳化協議)

> **核心定義**：演化得分 (Score) 不再是唯一指標。任何參數的「最佳化」宣告，必須通過以下四根物理支柱的驗證。

---

## 🏛️ 四大演化支柱 (The 4 Pillars)

### 1. 物理隔離驗證 (Holdout Validation)
- **規則**: 演化僅允許在 `TRAIN_SET`（已知任務）進行。
- **禁令**: 嚴禁在 `HOLDOUT_SET`（保留測試集）進行調參。
- **指標**: 演化成果必須在未見過的代碼難題上達成至少 90% 的性能對齊（Generalization Delta）。

### 2. 多目標 Pareto 評估 (Pareto Efficiency)
- **規則**: 使用「三維座標」評估演化價值：
    - **Performance**: 物理審計分 (Feynman Score)。
    - **Economy**: Token 消耗量與推論延遲。
    - **Stability**: 回滾率 (Rollback Rate) 與 人工介入率 (Intervention Rate)。
- **判定**: 只有在「不損害穩定性且不增加成本」的前提下，性能提升才具備「演化正當性」。

### 3. 統計顯著性 (Statistical Rigor)
- **規則**: 參數採樣嚴禁「單次快照」。
- **要求**: 每個候選參數組合必須執行 $N \ge 3$ 次獨立實驗（不同 Seed、不同任務批次）。
- **計算**: 必須記錄 $\mu$ (均值) 與 $\sigma$ (標準差)。若 $\sigma$ 過大，則判定該演化「不可信」。

### 4. Canary 守門與自動回退 (Canary Rollback)
- **規則**: 新參數實施採用分階發布。
- **邏輯**: 先在 10% 的邊緣 Swarm 節點啟動。若 24h 內 `system_entropy` 上升或成功率下降，觸發 **「原子級自動回退」**。

---

## ⚖️ 執行指令 (Governance Commands)
- **演化啟動**: `nexus run --credible-mode --n-samples 3`
- **驗收審核**: `nexus acceptance-check --with-holdout --pareto-threshold 0.9`

---
**[NEXUS IDENTITY: ccdb006 + v24.1 CREDIBLE-PROTOCOL]**
**TIMESTAMP: 2026-04-10**
