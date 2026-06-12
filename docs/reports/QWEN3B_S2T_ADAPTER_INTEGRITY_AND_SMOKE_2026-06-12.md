# Qwen2.5-3B-Instruct S2T 適配器完整性與 Smoke 測試報告

- **日期**: 2026-06-12
- **原始提交 Commit**: `99ec5850d2422caa6a45308639113ad9868e1066`
- **適配器等級 (Adapter Status)**: `canary advisor scaffold committed; real 3B advisory pending`

> [!WARNING]
> 本適配器僅使用嵌入式合成數據集 (`sim-task-0..34`) 進行訓練，主要用於驗證流程及工具鏈偵錯。**嚴禁**將此適配器部署至生產環境、作為預設路由，或將其混入任何運行時的 Gate 中。
> 若要晉升為運行時候選對象 (runtime candidate)，必須通過 Phase 5 影子評估階段，且至少需要 30 筆以上合格的真實 S2T Trace 數據。

---

## 🔒 適配器 SHA-256 校驗和 (Checksums)

這些雜湊值鎖定了本地下載的微調適適配器產物。本地的 Smoke 測試腳本會對其進行雙向校驗。

| 檔案名稱 | SHA-256 雜湊值 |
| --- | --- |
| `adapter_model.safetensors` | `6f2d7923bcfa93cfa1d4e4be0eb25ae6578d95f2ebec785cbe61e5bf89e2ca6c` |
| `adapter_config.json` | `a13cdbe6188f2a60f2fafdc51706a8460cfba7df996904d638d63a63bf46dd0d` |
| `tokenizer.json` | `3fd169731d2cbde95e10bf356d66d5997fd885dd8dbb6fb4684da3f23b2585d8` |
| `tokenizer_config.json` | `fbb05e8a722a05e92e8da2eabbb5820bbdd0d1482351a38cb14efa52fc8bdadb` |
| `chat_template.jinja` | `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f` |
| `README.md` | `a6f7b9573427cf03af8c5204cd9074efe8b86980790a1053283391b90168af40` |

---

## 🛠️ PEFT 配置驗證規格

- **基礎模型 (Base Model)**: `Qwen/Qwen2.5-3B-Instruct`
- **PEFT 類型**: `LORA`
- **LoRA Rank (r)**: `16`
- **LoRA Alpha (alpha)**: `32`
- **目標模組 (Target Modules)**: `["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]`
- **Bias 設定**: `none`
- **任務類型**: `CAUSAL_LM`

---

## 🧪 驗證執行指令

### 1. Mock 完整性校驗 (必要 Gate)
欲驗證檔案存在性、大小是否大於 0、PEFT 參數正確性以及雜湊值是否與此報告一致，請執行：
```bash
python3 scripts/train/smoke_test_adapter.py --verify-report docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
```

### 2. 結構化清單校驗 (Provenance Lock Gate)
欲使用程式化的 JSON 清單進行最嚴格的檔案大小、雜湊值及 Git Commit 追溯校驗（推薦）：
```bash
python3 scripts/train/smoke_test_adapter.py --verify-manifest docs/reports/qwen3b_s2t_adapter_manifest.json
```

### 3. 實體載入 Smoke 測試 (選用 Phase 5 前置條件)
欲在本地進行模型與適配器的合併載入測試，並驗證輸出 JSON Schema 合規性（使用本地快取權重，不聯網）：
```bash
python3 scripts/train/smoke_test_adapter.py --run-real --offline --device auto --timeout-sec 30
```

---

## 🏁 Gate 判定與採用檢查清單

- **[x] Git 污染防禦**: `.gitignore` 中已註冊忽略 `training/adapters/`、`scratch/qwen3b_s2t_adapter.tar.gz` 及 `.nexus/training/adapters/`。
- **[x] 訓練腳本安全化**: 已移除 `finetune_3b_student.py` 中所有的外部匿名上傳邏輯與 `verify=False` 參數。
- **[x] Phase 4.6 Adapter Manifest 鎖定**: 已生成結構化 `qwen3b_s2t_adapter_manifest.json` 綁定 commit `99ec5850`，並通過 `--verify-manifest` 校驗。
- **[ ] Phase 5.1 影子評估實體載入**: 通過 `--run-real --offline` 進行模型載入與固定 prompt JSON 輸出 Schema 比對。
- **[x] Phase 5.2-hard 影子數據鏈修復**: 已收緊為明確 `physical_verified=true` / `semantic_verified=true` / `claim_verified=true`，產生 35 筆去重 shadow rows，含 train/heldout split 與 source event hash。
- **[ ] Phase 5.3-real 影子評估 Gate**: `--emulator` 僅可產生 `OBSERVATION_ONLY` 報告；正式 Gate 仍需 `--run-real --offline` 通過，且 trust_mismatch_rate 不上升、selector 分歧附 reason code、parse/compliance 均 >= 95%。
- **[ ] Phase 6 運行時採用 Gate**: 僅以 strict-gated advisory (建議模式) 小比例放量運行，最終裁決仍歸 Rust 驗證器。
