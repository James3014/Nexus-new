# Walkthrough - Phase 4.6: Adapter Provenance Lock & Manifest 驗證完成

我們已成功實作並完成了 **Phase 4.6: Adapter Provenance Lock**。本階段透過將微調適配器產物的 checksums、PEFT 參數與 Git 歷史 commit `99ec5850` 進行物理鎖定，建立起不可混淆的溯源清單檔案。同時，擴充了 `smoke_test_adapter.py`，支援結構化的 JSON 雙向校驗。

## 🛠️ 主要修改內容

### 1. 結構化 Provenance 鎖定
- **`docs/reports/qwen3b_s2t_adapter_manifest.json`**:
  - 新增結構化清單。完整鎖定每個產物檔案名稱、大小與 SHA-256。
  - 將 PEFT LoRA 配置參數（base_model_id、r=16、peft_type=LORA、target_modules 等）寫入其中。
  - 記錄生成適配器的唯一 Git HEAD Commit `99ec5850d2422caa6a45308639113ad9868e1066`。

### 2. 校驗工具功能升級
- **`scripts/train/smoke_test_adapter.py`**:
  - 新增 `--write-manifest <path>`：自動掃描適配器產物、抓取當前 Git commit 並輸出 JSON。
  - 新增 `--verify-manifest <path>`：解析 JSON manifest，對比檔案雜湊與當前 Git commit 軌跡，確保沒有混淆或誤改。

### 3. 防禦邊界與採用報告更新
- **`docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md`**:
  - 標記 Phase 4.6 Provenance Lock 已全數通過。
  - 明確規劃 5 關卡防護清單，隔離「合成測試」與「運行時採用」。

---

## 🏁 後續 5 大採用關卡與進度

1. **[x] Phase 4.6: Adapter Provenance Lock (已通過)**：產出 manifest JSON，雙向綁定 commit `99ec5850` 與 checksums。
2. **[ ] Phase 5.1: Real Load Smoke (選用)**：載入模型並驗證 5 筆 sample JSON Schema。
3. **[ ] Phase 5.2: Shadow Dataset Repair (未啟動)**：修復 `selected_candidate_id: null` 資料鏈，過濾出至少 30 筆真實 shadow rows。
4. **[ ] Phase 5.3: S2T Shadow Eval Gate (未啟動)**：執行影子評估，確保 parse/compliance 均 >= 95%，且錯配率不上升。
5. **[ ] Phase 6: Limited Runtime Adoption (未啟動)**：以 strict-gated advisory 顧問模式（10% 起）進行生產環境放量。

---

## 🧪 驗證與測試證據

### 1. 產生結構化 Manifest
```bash
python3 scripts/train/smoke_test_adapter.py --write-manifest docs/reports/qwen3b_s2t_adapter_manifest.json
```
**輸出證實**:
```text
📝 Generating Adapter Manifest to docs/reports/qwen3b_s2t_adapter_manifest.json...
🎉 Manifest successfully written to docs/reports/qwen3b_s2t_adapter_manifest.json
```

### 2. Manifest 結構化清單校驗 (成功通過)
```bash
python3 scripts/train/smoke_test_adapter.py --verify-manifest docs/reports/qwen3b_s2t_adapter_manifest.json
```
**輸出證實**:
```text
🛡️ Verifying adapter using Manifest: docs/reports/qwen3b_s2t_adapter_manifest.json
✅ adapter_config.json checked: size and SHA-256 match.
✅ adapter_model.safetensors checked: size and SHA-256 match.
✅ tokenizer.json checked: size and SHA-256 match.
✅ tokenizer_config.json checked: size and SHA-256 match.
✅ chat_template.jinja checked: size and SHA-256 match.
✅ README.md checked: size and SHA-256 match.
🔎 Provenance Git Commit Check:
  Current HEAD Commit: 99ec5850d2422caa6a45308639113ad9868e1066
  Manifest Commit:     99ec5850d2422caa6a45308639113ad9868e1066
✅ Git provenance commit MATCH.
🎉 Manifest-based Integrity Check PASSED.
ℹ️ Physical load smoke test skipped (Use --run-real to execute).
```

### 3. Git 狀態
- 包含未追蹤的 `docs/reports/qwen3b_s2t_adapter_manifest.json` 與已修改的 `scripts/train/smoke_test_adapter.py`。
- 無任何 `.safetensors` 或大型權重檔案進入暫存區。
