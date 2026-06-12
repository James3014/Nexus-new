# Walkthrough - Phase 4.5: Qwen2.5-3B-Instruct 學生模型微調與安全校驗優化完成

我們已成功優化並完成了 **Phase 4.5: 3B 學生模型微調與本地完整性校驗** 的安全加固。本階段徹底解決了匿名外部上傳的安全風險，健全了本地 Smoke 測試腳本，確保了 Git 倉庫的純淨度，並明確設定了後續 Phase 5 與 Phase 6 的採用門檻（Gates）。

## 🛠️ 主要修改內容

### 1. 訓練腳本安全去匿名化
- **`scripts/train/finetune_3b_student.py`**:
  - 徹底移除了 `--upload` CLI 參數。
  - 移除了所有指向 `bashupload.com` 與 `transfer.sh` 的匿名上傳程式碼區塊。
  - 清除了所有 `verify=False` 的不安全 HTTPS 請求設定，杜絕 SSL 憑證繞過與外部數據外流風險，僅保留本地打包行為。

### 2. 本地驗證工具健全化
- **`scripts/train/smoke_test_adapter.py`**:
  - **超時控制**: 新增 `--timeout-sec` 參數，允許在執行實體模型加載與推論測試時設置硬性超時限制。
  - **自動設備選配**: `--device` 參數新增 `auto` 選項（並作為預設值），能自動依序檢測並使用 CUDA、MPS 或 CPU 設備。
  - **雙向 Checksum 校驗**: 將 `--verify-report` 預設路徑設為官方報告 `docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md`，實現開箱即用的雙向 SHA-256 雜湊核對。

### 3. 官方報告與 Git 防禦
- **`.gitignore`**:
  - 確實忽略了適配器資料夾 `training/adapters/`、壓縮檔 `scratch/qwen3b_s2t_adapter.tar.gz` 以及本地快取目錄 `.nexus/training/adapters/`。
- **`docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md`**:
  - 轉換為繁體中文版本。
  - 適配器等級明確定調為：`Adapter status: synthetic smoke adapter, not runtime adoption candidate`，以防 Phase 6 提早偷跑。

---

## 🏁 Phase 門檻與判定邊界

為了防止微調模型被提前非授權採用，我們建立了清晰的防護線：
1. **Phase 4.5 完成條件 (已通過)**: 
   - 官方完整性報告存在，且 SHA-256 雜湊與本地實體檔案雙向匹配。
   - Mock 完整性檢驗通過 (檢查 r=16, LORA, base_model, 7 大 projections)。
   - Git 零污染。
2. **Phase 5 前置條件**: 
   - 實體模型載入與推論測試通過，且輸出 JSON Schema 100% 合規。
3. **Phase 6 前置條件**: 
   - 至少 30 筆以上合格的真實 S2T 數據影子評估。
   - 完成 Rule Baseline 對照，且 `trust_mismatch_rate` (錯配率) 不上升。

---

## 🧪 驗證與測試證據

### 1. Mock 完整性校驗與報告對照 (成功通過)
我們在本地執行預設的雙向校驗，輸出結果如下：
```bash
python3 scripts/train/smoke_test_adapter.py
```
**輸出證實**:
```text
🛡️ Running Mock Integrity Check...
✅ All required adapter files present and non-empty.
✅ adapter_config.json settings match specifications (Qwen2.5-3B, LoRA r=16).
🔎 Verifying checksums against report: docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
✅ Hash MATCH for adapter_config.json: a13cdbe6...
✅ Hash MATCH for adapter_model.safetensors: 6f2d7923...
✅ Hash MATCH for tokenizer.json: 3fd16973...
✅ Hash MATCH for tokenizer_config.json: fbb05e8a...
✅ Hash MATCH for chat_template.jinja: cd8e9439...
✅ Hash MATCH for README.md: a6f7b957...
🎉 Mock Integrity Check PASSED.
ℹ️ Physical load smoke test skipped (Use --run-real to execute).
```

### 2. 離線 Fail-closed 安全保護測試 (成功通過)
若在無本地快取環境下試圖強制執行實體加載，會自動觸發 Fail-closed 阻斷：
```bash
python3 scripts/train/smoke_test_adapter.py --run-real --offline
```
**輸出證實**:
```text
🛡️ Running Mock Integrity Check...
✅ All required adapter files present and non-empty.
✅ adapter_config.json settings match specifications (Qwen2.5-3B, LoRA r=16).
🔎 Verifying checksums against report: docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
✅ Hash MATCH for adapter_config.json: a13cdbe6...
...
🎉 Mock Integrity Check PASSED.
🚀 Running Physical Load Smoke Test...
ℹ️ Offline mode active. Only local Hugging Face cache will be used.
🤖 Loading tokenizer for Qwen/Qwen2.5-3B-Instruct...
❌ Failed to load tokenizer locally (is model cached?): Offline mode is enabled and we couldn't find the cached files at /Users/jameschen/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots/...
❌ Physical load smoke test FAILED.
```

### 3. Git 污染狀態檢核 (無任何適配器洩漏)
```bash
git status --porcelain
```
- 無任何 `training/adapters/` 檔案或 `qwen3b_s2t_adapter.tar.gz` 進入 Git 追蹤範圍。
