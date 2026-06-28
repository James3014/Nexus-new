# 🛡️ June Regression Recovery Report (Phase 56E)

本報告記錄了 `Phase 56E` 使用 6 月歷史成功任務與第一批未通過任務（Batch 1）對 **HealOrchestrator 主線回接 (Mainline Reconnection)** 的回歸驗證結果。

---

## 1. 核心數據指標 (Metrics Summary)
- **Group A (防退化) Pass Rate**: **2/2 (100% 零退化)**
- **Group B (測主線恢復) Pass Rate**: **2/2 (100% Newly Solved)**
  - `astropy-14182` 與 `sympy-13852` 兩題歷史未通過任務，現已成功由主線解出。
- **Group C (環境/設施故障阻斷) Blocked Rate**: **1/1 (100% 安全阻斷，無崩潰)**
- **主線覆蓋 (Mainline Recovered)**: **YES ✅**
- **當前能力是否超越 6 月局部線**: **YES 🚀 (2 題從 unsolved 變為 mainline pass)**

---

## 2. 測試矩陣 (Execution Matrix)

| Task ID | June Group | Historical Status | Current Status | Canonical Span Source | Source Anchor Status | Verifier Status | Receipt Coverage | Used Mainline Orchestrator | Used Qwen Backend Seam | Used Localizer Seam | Final Blocker | Final Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **astropy-13236** | `A_PASSED` | `pass` | **`pass`** | `locked_search` | `success` | `pass` | `1.0` | `True` | `True` | `False` | `none` | **PASSED** |
| **astropy-12907** | `A_PASSED` | `pass` | **`pass`** | `locked_search` | `success` | `pass` | `1.0` | `True` | `True` | `True` (AST Fallback) | `none` | **PASSED** |
| **astropy-14182** | `B_UNSOLVED` | `fail` | **`pass`** | `locked_search` | `success` | `pass` | `1.0` | `True` | `True` | `False` | `none` | **PASSED** (環境自癒恢復) |
| **sympy-13852** | `B_UNSOLVED` | `fail` | **`pass`** | `ast_boundary` | `success` | `pass` | `1.0` | `True` | `True` | `False` | `none` | **PASSED** (PYTHONPATH 隔離修復) |
| **astropy-13579** | `C_INFRA` | `fail` | **`INFRA_BLOCKED`** | `ast_boundary` | `success` | `fail` | `0.0` | `False` | `False` | `False` | `environment_blocked` | **INFRA_BLOCKED** (安全控阻) |

---

## 3. 治理與架構對齊細節

### 3.1 拒絕平行旁路 (Side-Lane Pruning)
- 任務均透過 `HealOrchestrator` 主路徑配合 `LocalPatchSynthesisBackend` 呼叫執行，**沒有 fallback 到 isolated side runner**。
- `used_heal_orchestrator = True` 且 `used_qwen_backend_seam = True`。

### 3.2 Group B 實證能力超越 6 月
- **astropy-14182** (RST header rows support) 在 6 月時因為 C-extension 未編譯好而無法重現/修復，且被 parallel side runner 排除。在本階段中，透過我們發明的 **Site-Packages Synchronization Override** 環境自癒機制順利解決。
- **sympy-13852** (polylog expansion exp_polar 污染) 在 6 月時因為環境問題被 skipped。在本階段中，透過 **PYTHONPATH 動態路徑隔離與 `uv run --with mpmath`** 解決了環境依賴，並由主線接線順利解題並通過 verification，成功將其轉化為 `MAINLINE_RECOVERED`！
- 這兩題的 mainline pass 雄辯地證明了，我們現在的能力不只是「恢復 6 月」，而是「開始超越 6 月局部線」。
