# Nexus 5 大目標實作規格 (2026-03-19)

本文件定義了 `index.task.1` 至 `index.task.5` 的實作細節，Nexus Worker 應讀取此文件進行開發。

## 1. 導入 `phase_health` 落檔 (index.task.1)
- **目標**：確保 P-X-D-R-A-C 六階段執行完畢後，健康分值能物理持久化。
- **實作要求**：
    - 修改 `nexus/core/phase_health.py` 中的 `PhaseHealthCalculator`。
    - 增加 `save_to_json(path: Path)` 方法，將 `signals` 與 `health` 寫入 `.nexus/phase_health.json`。
    - 在 `NexusPipeline.run` 的每個階段結束時觸發寫入。
- **驗收標準**：執行後 `.nexus/phase_health.json` 必須存在且包含所有階段的分數。

## 2. 導入 `auto.repair.on_low_health` (index.task.2)
- **目標**：低健康度時自動觸發修復。
- **實作要求**：
    - 在 `task_runner.py` 中偵測 `phase_result_ok` 事件。
    - 若健康度低於閾值 (預設 80)，自動動態注入一條 `nexus:bug` 修復任務。
- **驗收標準**：當測試回傳低分時，Manifest 應出現臨時修復任務。

## 3. 導入 `learning_velocity` 與自動優化 (index.task.3)
- **目標**：根據學習速率調整策略。
- **實作要求**：
    - 修改 `nexus/core/policy/learning.py` 計算學習增量。
    - 若 `v <= 0`，嘗試切換更高階的模型或調整 Prompt 策略。
- **驗收標準**：`ci_benchmark.csv` 的 `v` 欄位不再恆為 0。

## 4. `ci_gate` 摘要更新 (index.task.4)
- **目標**：讓管理門檻更嚴格且透明。
- **要求**：`ci_gate.py` 的終端輸出與 `write_proof.json` 必須包含 `lowest_phase_health` 與 `learning_velocity`。

## 5. Raw Token 打通驗收 (index.task.5)
- **目標**：確保真實帳單數據 (raw > 0) 完整擷取。
- **要求**：驗算 `token_capture_status` 並產出對照報表，確保沒有幻覺數據。
