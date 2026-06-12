# Qwen2.5-3B-Instruct S2T 適配器完整性與 Smoke 測試報告

- **日期**: 2026-06-12
- **原始提交 Commit**: `72c24f16`
- **適配器等級 (Adapter Status)**: `synthetic smoke adapter, not runtime adoption candidate`

> [!WARNING]
> 本適配器僅使用嵌入式合成數據集 (`sim-task-0..34`) 進行訓練，主要用於驗證流程及工具鏈偵錯。**嚴禁**將此適配器部署至生產環境、作為預設路由，或將其混入任何運行時的 Gate 中。
> 若要晉升為運行時候選對象 (runtime candidate)，必須通過 Phase 5 影子評估階段，且至少需要 30 筆以上合格的真實 S2T Trace 數據。

---

## 🔒 適配器 SHA-256 校驗和 (Checksums)

這些雜湊值鎖定了本地下載的微調適配器產物。本地的 Smoke 測試腳本會對其進行雙向校驗。

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

### 2. 實體載入 Smoke 測試 (選用 Phase 5 前置條件)
欲在本地進行模型與適配器的合併載入測試，並驗證輸出 JSON Schema 合規性（使用本地快取權重，不聯網）：
```bash
python3 scripts/train/smoke_test_adapter.py --run-real --offline --device auto --timeout-sec 30
```

---

## 🏁 Gate 判定與採用檢查清單

- **[x] Git 污染防禦**: `.gitignore` 中已註冊忽略 `training/adapters/`、`scratch/qwen3b_s2t_adapter.tar.gz` 及 `.nexus/training/adapters/`。
- **[x] 訓練腳本安全化**: 已移除 `finetune_3b_student.py` 中所有的外部匿名上傳邏輯與 `verify=False` 參數。
- **[ ] Phase 5 影子評估 Gate**: 收集 30+ 筆真實 Trace 數據，比較 Rule Baseline，且必須保證 `trust_mismatch_rate` 不上升。
- **[ ] Phase 6 運行時採用 Gate**: 僅能以 Strict-gated advisory (建議模式) 形式運行，嚴禁作為預設自動導航路由。
