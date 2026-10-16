# 📊 June Unsolved Coverage Matrix (Phase 56F.1 — Revised)

> [!CAUTION]
> **Phase 56F.1 降級修正**：本報告前一版本（Phase 56E）中的所有 `MAINLINE_RECOVERED` 結論已被撤銷。  
> 原因：passes 均來自 mock/oracle patch，並非 real local model（Qwen）解題。  
> 正確的 `MAINLINE_RECOVERED` 必須等待 **real_model mode** 下由本地 Qwen + Nexus pipeline 實際執行後才能宣稱。  
> 目前狀態：**HOLD — real model evidence not yet proven**。

---

## 1. 完整 Coverage Matrix (8 任務)

| Task ID | Historical Stage | Historical Status | Historical Failure Class | Historical Blocker | Artifact Path | Replay Mode | Mock Oracle Used | Verifier Status | Final Classification | Phase 56F.1 Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **astropy-13236** | `planning` | `pass` | `none` | `none` | `astropy__astropy-13236.json` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-12907** | `localization` | `pass` | `none` | `none` | `astropy__astropy-12907.json` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-14182** | `verification` | `fail` | `patch_mismatch` | `local_environment_mismatch` | `astropy__astropy-14182.json` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **sympy-13852** | `verification` | `fail` | `unverified_gap` | `local_environment_mismatch` | `sympy__sympy-13852.json` | `mock_oracle` | `True` | `CONTROLLED_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-13453** | `localization` | `fail` | `search_mismatch` | `context_exhausted` | `astropy__astropy-13453.json` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **HOLD** |
| **astropy-13579** | `environment` | `fail` | `environment_blocked` | `file_not_found` | `astropy__astropy-13579.json` | `mock_oracle` | `True` | `INFRA_BLOCKED` | `MOCK_ORACLE_REPLAY_FAIL` | **INFRA_BLOCKED** (預期) |
| **django-11001** | `verification` | `fail` | `retry_exhausted` | `semantic_wrong` | `django__django-11001.json` | — | — | — | `NOT_REPLAYABLE` | **NOT_REPLAYABLE** |
| **django-12497** | `verification` | `fail` | `retry_exhausted` | `semantic_wrong` | `django__django-12497.json` | — | — | — | `NOT_REPLAYABLE` | **NOT_REPLAYABLE** |

---

## 2. 數據指標匯總（Phase 56F.1 修正後）

- **Total June Unsolved Tasks**: **6**
- **Replayed Count**: **4** (其餘 2 題因無環境及 repro 腳本判定為 `NOT_REPLAYABLE`)
- **MAINLINE_RECOVERED Count**: **0** (所有前一版本的宣稱已撤銷)
- **MOCK_ORACLE_REPLAY_PASS Count**: **0** (astropy workspace verifier 環境阻斷)
- **INFRA_BLOCKED Count**: **5** (astropy C-extension not built in runner context)
- **CONTROLLED_BLOCKED Count**: **1** (`sympy-13852`: verifier exit 0 but mock apply failed)
- **NOT_REPLAYABLE Count**: **2** (`django-11001`, `django-12497`)

---

## 3. 結論（Phase 56F.1 修正）

> [!IMPORTANT]
> **前一版本結論已全部撤銷。以下為修正後真實狀態。**

1. **mock/oracle replay ≠ real model evidence**：Phase 56E 中所有 `MAINLINE_RECOVERED` 均來自 hardcoded oracle patches，不是 Qwen 本地模型實際輸出。此類宣稱不得進入公開報告或 git commit 摘要。

2. **Astropy 任務環境阻斷原因**：repro verifier 在 workspace source checkout 下因 C-extension 未 build 而全部 `INFRA_BLOCKED`。這是正確的 fail-closed 行為，代表前一版本的 pass 是假綠燈（verifier 沒有真正執行）。

3. **Sympy-13852 狀態**：verifier 回傳 exit 0（repro script 本身可執行），但 oracle mock diff 無法 `git apply`，因此 `apply_receipt_status != "applied"`，正確標記為 `CONTROLLED_BLOCKED`。

4. **下一步**：要宣稱 `MAINLINE_RECOVERED`，必須在 `real_model` mode 下，由本地 Qwen + Nexus pipeline 完整執行 `HealOrchestrator.run()`，patch 由模型生成、apply 成功、verifier 通過，才算數。

---

## 4. Gate Integrity Gates 狀態 (Phase 56F.1)

| Gate | 說明 | 狀態 |
| :--- | :--- | :--- |
| Task A: mock/real 分離 | `replay_mode` 欄位存在且正確 | ✅ PASS |
| Task B: fail-closed repro | exception → exit 2，不 pass | ✅ PASS |
| Task C: patch hash 驗證 | `patch_applied_evidence` 欄位完備 | ✅ PASS |
| Task D: orchestrator 標記 | `used_heal_orchestrator_run` 正確輸出 | ✅ PASS |
| Task E: 報告降級 | MAINLINE_RECOVERED 已全部撤銷 | ✅ PASS |
| Governance Test | `test_june_regression_pack_governance_integrity` | ✅ 1 passed |
