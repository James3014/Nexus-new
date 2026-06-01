[NEXUS v26 ACTIVE]

# 📄 Nexus 交接報告：環境規約防禦與模型鎖定 (Stop & Handoff)

**狀態：SAFE & FAIL-CLOSED**
**交接時間：2026-06-01**

## 1. 任務現況總結
前置任務已完成對 Nexus 管線的環境防禦強化，並成功鎖定模型路線，確保在環境與模型配置未達標前，絕不進入正式的 Patch 階段。

- **模型路線鎖定**：正式 lane 已經對齊為 **Ollama `qwen2.5-coder:7b/14b`**。已在 `swe_local_heal.py` 中移除所有 LM Studio/qwen3.5 的邏輯，防止文字污染。
- **環境預檢強化**：Astropy 類任務的 preflight 現在不只檢查 Python 次要版本，還會**真實執行 import** 以驗證語義相容性。
- **TDD 防禦建立**：已建立 `tests/unit/test_env_resolver_imports.py`，明確測試：若 checkout 需要 `typing.Self`，則**不得選擇 Python 3.9/3.10**，並已通過驗證。

## 2. 阻斷點診斷 (Blocker)
針對 `astropy__astropy-12907`：
1. **Env Parity 未閉合**：該題目在 Python 3.10 下重現時會出現 `ImportError: cannot import name 'Self' from 'typing'`，這代表 `astropy-legacy` profile (預設 Python 3.9/3.10) 與此 checkout 不相容。
2. **Profile 衝突**：目前 `astropy-311` profile 雖然能通過 `typing.Self` 的檢查，但其虛擬環境（`.venv_astropy_311/bin/python` = Python 3.11.14）內安裝的 numpy 版本是 `2.4.6`，違反了我們為了向下相容所設立的 `numpy < 2.0.0` 約束。

因此，**`astropy__astropy-12907` 目前的狀態是 `ENV_BLOCKED`，尚未進入合法 patch 階段。**

## 3. 給下一位 Agent 的行動指令

你現在接手 Nexus 的環境配置任務。請**嚴格遵守**以下步驟，**不要**嘗試啟動模型的 patch 過程：

1.  **專注修復 Profile**：先處理 `astropy__astropy-12907` 的 environment profile。你需要解決「需要 Python 3.11+ (為了 typing.Self)」與「需要 numpy < 2.0.0」之間的衝突。
    *   *提示*：你可以考慮調整 `astropy-311` profile 的 `package_constraints`，或是為這個特定的 checkout 建立一個新的 profile (例如 `astropy-12907-specific`)，並確保對應的虛擬環境安裝了正確版本的 numpy。
2.  **維持 Ollama 路線**：不要再用 LM Studio。正式 lane 固定為 Ollama `qwen2.5-coder:7b/14b`。
3.  **驗證 Preflight**：修正環境配置後，先跑 `ci_gate.py` 或針對該題的 `preflight`。
4.  **禁止提前 Patch**：只有在 preflight 完全通過（環境 parity 閉合）後，才允許推進到正式的 single-task repair。若環境未準備好，系統必須保持 fail-closed 狀態。

---
[NEXUS IDENTITY: 384c6fd02 + v2.9 RUNTIME-ALIGNED]
