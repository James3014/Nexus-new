# Walkthrough - Phase 5 & Phase 6: Canary Advisor Scaffold Committed & Real Advisory Pending

我們已建置並提交 **Phase 6 Canary Advisor Scaffold** 的腳本與測試架構。目前的 3B 模型本體尚未正式被採用於實體運行時，正處於 `real 3B advisory pending` 階段。本階段我們已逐步加固 Fail-Closed 實體影子評估 (Phase 5.3-real)、收緊訓練數據過濾門檻 (Phase 5.2-hard)，並實作僅供監控觀察、絕不干預運行時裁決的 10% Observation Canary 機制。

---

## 🛠️ 主要修改內容

### 1. 影子數據鏈收緊與去重 (Phase 5.2-hard)
- **`scripts/ops/export_3b_student_data.py`**:
  - **驗證過濾收緊**: 僅接受 `physical_verified == true` 或 `semantic_verified == true` 或 `claim_verified == true` 的 Row，不再使用 `verifier_result == "pass"` 作為寬鬆放行條件。
  - **任務去重 (Deduplication)**: 引入 `seen_task_ids`，確保同一個 `task_id` 不會重複出現在訓練集中。
  - **決定性 Split 劃分**: 基於 `task_id` 的 MD5 雜湊，將資料集以 80/20 比例決定性切分為 `train` 與 `heldout` 集合。
  - **雜湊溯源**: 於導出的資料列中新增 `source_event_hash` 欄位以追溯原始 JSON 記錄。
  - **執行狀態**: 導出 35 筆去重後的高品質 shadow rows，成功生成 `.nexus/training/dataset_card.json` 且狀態為 `VALIDATED`。

### 2. 實體 Fail-Closed 影子評估 (Phase 5.3-real)
- **`scripts/bench/s2t_shadow_eval.py`**:
  - **Fail-Closed 機制**: `--run-real` 模式下，若 Transformers / Peft 庫或適配器權重載入失敗，會直接拋出錯誤並 `sys.exit(1)` 退出，防止自動 fallback 到 emulator 模式。
  - **顯式仿真器**: 只有在命令中指定 `--emulator` 時，才會啟動仿真器評估。
  - **報告追溯擴展**: 報告中加入 `eval_mode` (取值為 `real` 或 `emulator`)，以及 `adapter_sha256`、`dataset_sha256`、`commit_sha`。
  - **驗證結果**:
    - 跑 `--run-real --offline --timeout-sec 900` 於無 peft 環境下如預期 Fail-Closed 阻斷 (exit 1)。
    - 跑 `--emulator` 成功輸出評估報告，JSON Parse Rate 和 Schema Compliance 均維持 `100.0%`。

### 3. 實體 Advisor 與 Observation Canary (Phase 6.1 & 6.2)
- **`nexus/services/s2t_strict.py`**:
  - **`S2T3BAdvisor` 介面**: 實作 base model + LoRA 載入與推論；若載入失敗或不合規則 abstain，僅在測試顯式注入 `force_simulation=True` 時使用仿真器。
  - **不篡改決策**: `S2TStrictRuntimeGate.evaluate` 僅調用 advisor 提供推薦，最終 passed 與 selected id 仍完全遵循 baseline，絕不被 advisor override。
  - **收緊 telemetry 記錄**: Canary telemetry log 增加 `advisor_parse_schema_verdict`、`trust_mismatch`、以及動態 ISO 8601 時間戳 `timestamp_utc`。

### 4. 單元測試驗證 (TDD Guard)
- **`tests/gates/test_s2t_claim_gate.py`**:
  - 新增 `test_s2t_strict_gate_evidence_log_format` 以驗證當 10% canary 觸發時，產生的 `.jsonl` telemetry evidence row 包含完整的 dynamic timestamp、baseline selected ID、advisor selected ID、advisor verdict、verifier result、與 trust mismatch。
  - **測試結果**: 執行 `pytest tests/gates/` 共 8 筆測試全數 **PASSED**。

---

## 🧪 驗證與測試證據

### 1. 影子數據集修復匯出
```bash
python3 scripts/ops/export_3b_student_data.py
```
**輸出證實**:
```text
✅ Exported 35 rows. Status: VALIDATED
📄 Dataset card saved to .nexus/training/dataset_card.json
```

### 2. Fail-Closed 實體載入阻斷測試
```bash
python3 scripts/bench/s2t_shadow_eval.py --run-real --offline --timeout-sec 900
```
**輸出證實 (Exit Code 1)**:
```text
🔎 Starting S2T Shadow Evaluation on .nexus/training/s2t_3b_student_v1.jsonl...
📊 Loaded 35 evaluation rows. Mode: real
🤖 Attempting to load real 3B model for prediction...
❌ Fail-closed: Real model load failed: No module named 'peft'
```

### 3. 仿真器評估報告產出
```bash
python3 scripts/bench/s2t_shadow_eval.py --emulator --output .nexus/metrics/s2t_shadow_eval_report.json
```
**輸出證實**:
```text
🔎 Starting S2T Shadow Evaluation on .nexus/training/s2t_3b_student_v1.jsonl...
📊 Loaded 35 evaluation rows. Mode: emulator
🎉 Shadow evaluation complete. Output saved to .nexus/metrics/s2t_shadow_eval_report.json
  Mode:                  emulator
  JSON Parse Rate:       100.0%
  Schema Compliance:     100.0%
  Override Verified Lift: 100.0%
  Status:                OBSERVATION_ONLY
```

### 3. 運行時採用與分流單元測試
```bash
uv run pytest tests/gates/
```
**輸出證實**:
```text
tests/gates/test_s2t_claim_gate.py::test_s2t_claim_gate_blocks_public_claim_without_gate_evidence PASSED
tests/gates/test_s2t_claim_gate.py::test_s2t_claim_gate_passes_verified_public_claim_with_evidence PASSED
tests/gates/test_s2t_claim_gate.py::test_s2t_strict_gate_advisor_triggers_on_matching_canary PASSED
tests/gates/test_s2t_claim_gate.py::test_s2t_strict_gate_advisor_ignores_non_matching_canary PASSED
tests/gates/test_s2t_delivery_gate.py::test_s2t_delivery_gate_blocks_when_no_verified_candidate_exists PASSED
tests/gates/test_s2t_delivery_gate.py::test_s2t_delivery_gate_passes_verified_candidate PASSED
============================== 8 passed in 0.17s ===============================
```

---
*驗證者: Antigravity*
*日期: 2026-06-12*
