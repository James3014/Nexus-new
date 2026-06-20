# V7-A — Dogfood Execution Approval Packet

**Status**: AWAITING_OWNER_DECISION
**Owner Decision**: [Pending Sir's Command]

---

## 1. Candidate Task List

本階段狗食執行候選任務名單包含 3 個初始執行任務與 2 個備份任務：

### 初始狗食任務 (Initial Tasks)

1.  **MC001 (astropy__astropy-13236)**
    *   **專案路徑**: `/Users/jameschen/Workspace/nexus/artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: `95df21d`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期 Verifier 指令**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3 -m pytest`
    *   **解釋器與虛擬環境**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3`
    *   **依賴風險**: **LOW**。環境在先前 V4-A 中已建置完成並跑通。
    *   **選取理由**: Direct model patch 成功代表案例，檢驗 AST slicing 與 patch protocol。
    *   **狗食安全評估**: 只修改 `astropy/table/table.py` 型態邏輯，不涉及系統 API 或網絡調用，且測試套件支援 time-out 限制。

2.  **MC006 (sympy__sympy-13852)**
    *   **專案路徑**: `/Users/jameschen/Workspace/nexus/artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `e228d7a`
    *   **預期通道 (Expected Lane)**: `canonical_recovery_success`
    *   **預期 Verifier 指令**: `/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3 -m pytest sympy/core/tests/test_numbers.py`
    *   **解釋器與虛擬環境**: `/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3`
    *   **依賴風險**: **LOW**。
    *   **選取理由**: Sympy 專案中針對 canonical recovery（典型空白或換行修剪）之代表案例。
    *   **狗食安全評估**: Sympy 專案為純代數邏輯，執行期不觸及 I/O 破壞，執行安全。

3.  **MC007 (astropy__astropy-12907)**
    *   **專案路徑**: `/Users/jameschen/Workspace/nexus/artifacts/external_sources/astropy_13236` (不同 Instance)
    *   **預期 Base Commit**: `95df21d`
    *   **預期通道 (Expected Lane)**: `verifier_passed_by_execution`
    *   **預期 Verifier 指令**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3 -m pytest astropy/modeling/tests/test_separable.py -x`
    *   **解釋器與虛擬環境**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3`
    *   **依賴風險**: **LOW**。
    *   **選取理由**: 測試 Direct model patch 的跨模組適用性（modeling/separable.py）。
    *   **狗食安全評估**: 範圍侷限在 Modeling 單一檔案內，測試套件不具備網路依賴性。

### 備份任務 (Reserve Tasks)

4.  **V4B_12481 (sympy__sympy-12481)**
    *   **專案路徑**: `/Users/jameschen/Workspace/nexus/artifacts/external_sources/sympy_13852`
    *   **預期 Base Commit**: `8059df7`
    *   **預期通道 (Expected Lane)**: `canonical_recovery_success`
    *   **預期 Verifier 指令**: `/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3 -m pytest sympy/ -x --timeout=60`
    *   **解釋器與虛擬環境**: `/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3`
    *   **依賴風險**: **MEDIUM**。先前曾有 NO_BLOCKS_FOUND 警告。
    *   **選取理由**: Canonical recovery 錯誤路徑防護控制案例。
    *   **狗食安全評估**: Sympy 環境完全物理隔離。

5.  **MC008 (astropy__astropy-14182)**
    *   **專案路徑**: `/Users/jameschen/Workspace/nexus/artifacts/external_sources/astropy_13236`
    *   **預期 Base Commit**: 相同 astropy
    *   **預期通道 (Expected Lane)**: `env_blocked_but_review_verified`
    *   **預期 Verifier 指令**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3 -m pytest astropy/ -x --timeout=60`
    *   **解釋器與虛擬環境**: `/Users/jameschen/Workspace/nexus/.venv_astropy_repair/bin/python3`
    *   **依賴風險**: **HIGH**。用以模擬環境阻塞下的 fail-closed 是否能被 compliance checker 正確歸檔。
    *   **選取理由**: Blocker 物理攔截通道穩定性測試。
    *   **狗食安全評估**: 測試會被 preflight block，中斷後續 model 調用，極度安全。

---

## 2. Execution Policy

狗食執行過程中，模型策略與治理邊界限制如下：
*   **7B Default**: 必須將 `qwen2.5-coder:7b` 作為預設主要執行器。
*   **14B Fallback**: `qwen2.5-coder:14b` 只能做為手動 escalation 備選，且必須在 7B semantic failure 後，經由 owner 明確核准始能啟動，且強制套用 **Strict prompt**。
*   **3B Advisory**: `qwen2.5:3b` 僅可用於 advisory audit（如審計與 lane 預估），禁止產生實體修復程式碼。
*   **物理硬合規**: `runbook_compliance` checker 在每次任務結束後 mandatory 執行。
*   **嚴格物理邊界**: 
    *   禁止對外公開宣稱（`public_claim_allowed = false`）。
    *   禁止導出做訓練數據（`training_eligible = false`）。
    *   禁止開啟自動模型路由與運行時整合。

---

## 3. Per-Task Gate Checklist

每一次狗食執行任務必須依序通過以下 10 道審查閥門：

*   **G0: Task Eligibility**: 核對 task_id、預置 repo 狀態。
*   **G1: Source Checkout**: 物理檢查 source git sha 並還原至 clean state。
*   **G2: Baseline Reproduction**: 驗證 baseline 測試失敗。
*   **G3: Task-Scoped Verifier**: 建立 MicroVerifier 獨立測試上下文。
*   **G4: Model Execution**: Ollama 調用 7B (或 strict 14B) 產出 patch。
*   **G5: Patch Authority**: 核對程式碼修補與 SSoT 的一致性（verbatim / canonical_recovery）。
*   **G6: Final Verifier**: 實體 pytest 跑通且 100% 綠燈。
*   **G7: Export Classification**: 歸檔為合格之成功/阻塞標記。
*   **G8: Governance**: 核對是否違反 global constraints（如 cloud_api_used, training_eligible 等）。
*   **G9: Owner Acceptance**: 呈交 final 報告供 Owner 審查。

---

## 4. Stop Rules

若在執行期間觸發以下任何一項條件，**必須立刻中止流程並向 Owner 回報**：

1.  **Global Stop Rules**:
    *   `public_claim_allowed=true`
    *   `training_eligible=true`
    *   `runtime_integration_enabled=true`
    *   `routing_integration_enabled=true`
    *   `model_calls=0` 但被標記為 model_patch_success。
    *   成功修復任務的 `match_authority=None`（env-blocked 除外）。
    *   `FUZZY_CANDIDATE_ONLY` 被歸類為 model success。
    *   `canonical_recovery` 坍縮為 direct model success。
    *   `env_blocker` 被歸類為 model success.
    *   `task_scoped=false` 且 verifier 跑通。
    *   14B 執行未提供 strict prompt evidence，或被標記為 default executor。
    *   3B 被當成 executor 生成 patch。
    *   未調用 compliance checker，或 checker 回報 hard-fail。
2.  **Per-Task Stop Rules**:
    *   測試執行期間偵測到對外聯網請求。
    *   偵測到需載入生產環境或 private credentials。
    *   出現 codebase worktree 污染或寫入鎖定失效。

---

## 5. Required Artifacts Per Task

每次執行必須在 `artifacts/runtime/v7b_internal_dogfood_execution_v0/<task_id>/` 下產出以下 9 項物理證據：

1.  `environment_preflight.json` — 環境與 OS 預檢。
2.  `baseline_reproduction.json` — 缺陷重現事實。
3.  `model_execution.json` — 7B/14B Ollama 輸入與輸出（若進入 model 階段）。
4.  `patch_authority_receipt.json` (或 `blocker_classification.json`) — patch 權重事實。
5.  `final_verification.json` — 修補後 Verifier 執行結果。
6.  `real_replay_result.json` — 完整執行綜合收據。
7.  `receipt_audit.md` — 易讀版人工檢視收據。
8.  `compliance_result.json` — `runbook_compliance` checker 的輸出結果。
9.  `trace_internal_audit.json` — 內部同步用 trace payload。

---

## 6. Owner Approval Options

請 Sir 回覆以下其中一個指令以進行下一步路由：

*   **選項 A**: `APPROVE_V7B_DOGFOOD_EXECUTION_FIRST_3_TASKS`
    *(核准對 MC001, MC006, MC007 進行實體 V7-B 狗食執行)*
*   **選項 B**: `APPROVE_V7B_DOGFOOD_EXECUTION_ONE_TASK_ONLY`
    *(僅核准執行 MC001 任務，完成後停等)*
*   **選項 C**: `DEFER_DOGFOOD_EXECUTION`
    *(延後狗食執行，Agent B 進入 V8-A 之後的非執行規劃/分析)*
*   **選項 D**: `REQUEST_TASK_SELECTION_REWORK`
    *(重新進行任務篩選)*
