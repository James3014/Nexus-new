# Y2 — Controlled Multi-Anchor / Multi-File Action Protocol Report

**狀態**: `Y2_MULTI_ANCHOR_PROTOCOL_READY`, `Y2_TWO_FILE_PROTOCOL_DESIGNED_OWNER_GATED`, `Y2_PROTOCOL_DIAGNOSTIC_ONLY`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 容許之行動協議與安全守則 (Allowed Protocols & Safety Rules)
為了在維持安全 invariants 的前提下解鎖更難的任務修復，我們設計並實現了五大行動協議：
1.  **MULTI_ANCHOR_SEQUENCE**: 適用於單一檔案多個關聯 span 的序列修改。
2.  **TWO_FILE_COORDINATED_EDIT**: 適用於雙檔案因果協調修改。
3.  **API_COMPATIBILITY_ADAPTER**: 產生相容適配層。
4.  **STATE_PROPAGATION_FIX**: 一處修改狀態，另一處使用。
5.  **ABSTAIN_BOUNDARY_EDIT**: 針對超出安全 limits 的修改進行主動拒絕並轉 owner 審批。

### 核心安全門禁 (Safety Verification Rules)
- **個體可解析性**: 每一處 ProtocolAction 均為 bounded、有 exact_search_text 與 evidence node 軌跡。
- **雙檔案強制審核**: 當 protocol_type 為 `TWO_FILE_COORDINATED_EDIT` 時，必須強制設定 `owner_approval_required = True`。若未設定，則驗證器在 `validate_protocol()` 時會直接回傳拒絕，防止假綠燈。
- **Abstain 拒絕門禁**: 當編輯跨檔案數量大於 2 或 actions 數量大於 5 時，直接強制轉換為 `ABSTAIN_BOUNDARY_EDIT` 進行阻斷，拒絕執行修補。

---

## 2. 核心任務行動協議設計與阻斷實例

### Sympy-14096 (MULTI_ANCHOR_SEQUENCE)
- **結構**: 單一檔案 `sympy/core/power.py` 下的 `Pow._eval_is_integer` 修改。
- **驗證**: 無需 owner approval，但必須通過 verifier 驗收。
- **Example**: [protocol_examples.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y2_controlled_multifile_protocol_v0/protocol_examples.json) 中的 `sympy__sympy-14096`。

### Django-11505 (TWO_FILE_COORDINATED_EDIT - Owner Gated)
- **結構**: base.py add 方法與 cookie.py _encode 方法協同修改，兩處編輯有序列依賴。
- **驗證**: 標記 `owner_approval_required = True`。在沒有 Owner 手動授權前，該修復處於 Gated Block 狀態，僅用於 Diagnostic。
- **Example**: [protocol_examples.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y2_controlled_multifile_protocol_v0/protocol_examples.json) 中的 `django__django-11505`。

### Django-13455 (ABSTAIN_BOUNDARY_EDIT)
- **結構**: 因修改牽涉 compiler.py, query.py, models.py 三個以上檔案，超出安全 limit。
- **驗證**: 動態產出 `ABSTAIN_BOUNDARY_EDIT`，列明 `abstain_reason`。
- **Example**: [blocked_boundary_examples.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/y2_controlled_multifile_protocol_v0/blocked_boundary_examples.json) 中的 `django__django-13455`。

---

## 3. 結論與下一步
安全多檔案行動協議已成功實現防禦性邊界。下一步，我們將執行 Y3 前沿基準對照跑測，衡量此協議在五大 Policy 中的表現與 14B fallback 模型效益。
