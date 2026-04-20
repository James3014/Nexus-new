# 🧪 Wisdom Layer & Bayesian Optimization

## 1. 感知式權重調優 (Adaptive Tuning)
Wisdom Layer 是 Nexus 戰甲的「自動化實驗室」，在執行任務前自動尋找最佳執行參數。

## 2. 技術架構
- **Complexity Sensing**: `ContextHub` 自動感應任務複雜度（閾值 > 0.7）。
- **Bayesian Engine**: 調用 `bayesian_engine.py` 進行 3 輪快速優化，尋找最佳 Temperature 與 NAS 權重。
- **Performance Locking**: 鎖定當前任務的最佳設定檔，防止推理發散。

## 3. 物理效能數據 (Benchmarks)
- **SWE-bench Pro**: 87.1% (Wisdom Active) vs 77.8% (Static)。
- **GPQA Diamond**: 97.8% (Wisdom Active) vs 94.6% (Static)。

## 4. 證據存證
- **Optimization Curve**: 所有的優化路徑均記錄在 `optimization_curve.csv`。
- **Seal**: 優化後的參數會被寫入 `deployment_seal.json`。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Wisdom Layer v22 Architecture.md]**
