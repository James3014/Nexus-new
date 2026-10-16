# 🛡️ June Regression Recovery Report (Phase 56F.1 — Revised)

> [!CAUTION]
> **Phase 56F.1 降級修正**：本報告前一版本（Phase 56E/F）中的所有 `PASSED` 與 `MAINLINE_RECOVERED` 結論已被撤銷。  
> 原因：所有 pass 均來自 hardcoded mock/oracle patches，**不是本地 Qwen 模型實際生成的 patch**。  
> 前一版本的 verifier 並未真正執行（環境阻斷後 false pass），且 repro 例外處理 fail-open。  
> 目前狀態：**HOLD — real model evidence not yet proven**。

---

## 1. 核心數據指標（Phase 56F.1 修正後）

- **Group A (防退化) Real Model Pass Rate**: **UNKNOWN** (需要 `real_model` mode 執行)
- **Group B (主線恢復) Real Model Pass Rate**: **UNKNOWN** (需要 `real_model` mode 執行)
- **Group C (INFRA) INFRA_BLOCKED**: **1/1** (正確標記)
- **主線覆蓋 (MAINLINE_RECOVERED)**: **0** (前版本宣稱已全部撤銷)
- **當前能力是否超越 6 月局部線**: **UNKNOWN — 需要 real_model mode 驗證**

---

## 2. 測試矩陣（Phase 56F.1 修正後 — mock_oracle mode）

| Task ID | June Group | Historical Status | replay_mode | mock_oracle_used | Verifier Status | Final Classification | Phase 56F.1 Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **astropy-13236** | `A_PASSED` | `pass` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-12907** | `A_PASSED` | `pass` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-14182** | `B_UNSOLVED` | `fail` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **sympy-13852** | `B_UNSOLVED` | `fail` | `mock_oracle` | `True` | `CONTROLLED_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-13453** | `B_UNSOLVED` | `fail` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-13579** | `C_INFRA` | `fail` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **INFRA_BLOCKED** (預期) |

---

## 3. Phase 56F.1 Gate Integrity 治理細節

### Gate A — mock/real 分離
- `NEXUS_REGRESSION_MOCK_LLM = 1` 預設已移除，改由 `--replay-mode` 指定。
- 所有任務 `mock_oracle_used = True`，`real_model_called = False`。

### Gate B — fail-closed repro 修正
- 所有 `repro_code` 中的 exception 已修正：`ImportError/ModuleNotFoundError → exit 2`，`bug present → exit 1`，`success → exit 0`。
- 前一版本的 broad `except Exception: sys.exit(0)` 已全部清除。

### Gate C — patch hash 驗證
- `patch_applied_evidence` 欄位已完備輸出：`candidate_patch_hash`, `applied_patch_hash`, `patched_file_hash_before`, `patched_file_hash_after`, `apply_receipt_status`, `verifier_ran_after_apply`。
- astropy 任務均為 `INFRA_BLOCKED`，`apply_receipt_status = "mock_oracle_injected"` 但 verifier 未通過。

### Gate D — orchestrator 標記
- `used_heal_orchestrator_run = True` (所有有嘗試的任務)。
- 不再使用 `_run_repair_loop` 直接呼叫，已升級為 `HealOrchestrator.run(ctx)`。
- 由於使用 FakePhase 替代真實 Linear Phases，標記為 `REPAIR_LOOP_SEAM_PASS` 而非 `FULL_MAINLINE_RECOVERED`。

### Gate E — 報告降級
- 本報告（`june_regression_pack_v0.md`）已降級。
- `june_unsolved_inventory_v0.md` 已降級。
- `june_unsolved_coverage_matrix_v0.md` 已降級。
- 所有 `MAINLINE_RECOVERED` 宣稱已撤銷，標記為 `HOLD`。

---

## 4. 前一版本問題根因 (Codex 審查確認)

1. **Pass 來自 mock/oracle patch，不是 real model**：`run_june_regression_pack.py` 強制 `NEXUS_REGRESSION_MOCK_LLM = 1`，`LocalPatchSynthesisBackend` 直接返回 hardcoded diff。
2. **Repro exception fail-open**：`except Exception: sys.exit(0)` 導致任何環境錯誤都被視為 pass。
3. **Verifier 沒有真正執行**：前版本在 site-packages 注入後以 `PYTHONPATH = workspace_path` 執行，astropy 因 C-extension 未 build 導致 `ImportError`，但 exception handler 吃掉後回報 pass。
4. **runner 不是完整 HealOrchestrator.run()**：前版本直接呼叫 `_run_repair_loop(ctx, ledger)`，跳過了 Reproduction、Planning、Localization 三個線性階段。
