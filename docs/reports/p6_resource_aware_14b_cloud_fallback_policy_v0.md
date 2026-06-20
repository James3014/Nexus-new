# Resource-Aware 14B and Cloud Fallback Policy Design (P6)

本文件定義 **P6 — Resource-Aware 14B and Cloud Fallback Policy Design**。為了防止本機 CPU 推理引起系統 OS Hang，且在小模型能力受阻時有安全的升級路徑，建立本項治理政策。

## 1. 本機 14B / 12B 大模型執行政策

### A. 准許執行條件
本機 CPU 僅在滿足以下所有條件時，才允許調用 Gemma 12B 等大模型：
1. **Resource Guard 驗證通過**: 系統 Free Memory >= 4.0 GB，且 Swap Activity 處於正常區間，未發生磁碟 IO 飽和。
2. **Strict Prompt 規則存在**: 載入了專屬的大模型精準引導 Prompts，以限縮其生成長度（`num_predict <= 768`）。
3. **Semantic 瓶頸**: 前次的失敗原因已被定位為邏輯語意錯誤（例如 semantic_wrong），而不是環境不相容或 parse 失敗。
4. **記錄 Owner 核准代碼**: telemetry 需記錄 `fallback_reason = "owner_approved_semantic_escalation"`.

### B. 絕對禁止執行條件
在以下任何情況下，本機大模型執行應被 **Fail-Closed 阻斷**：
1. 本機 CPU 推理有記憶體耗盡（OOM）或引發 OS Hang 的風險。
2. 上一次大模型執行所造成的系統 OS Hang 未能完全排除或定位原因。
3. 未成功建立 reproduction 腳本或原始碼版本不正確。
4. 核心失敗原因為 `ENV_BLOCKED`（環境不相容或解譯器缺失）。在此情況下，調用大模型只會浪費資源，應直接 fail-closed。

---

## 2. 雲端 Fallback 設計政策 (Design Only)
當本機 7B/12B 均無法解決語意瓶頸，且需要使用雲端大模型（如 Gemini API）時，執行以下安全合約：
1. **明確核准**: 每次雲端調用必須事先獲得 Owner 的單次/批次授權，禁止默認啟用。
2. **Telemetry 記錄**: 必須明確記錄 `cloud_api_used=true`。
3. **成果歸屬隔離**: 雲端大模型的修復成果 **絕對不能** 被計入本地 7B/12B 模型的自研成功率，應獨立歸類為 `cloud_assisted_patch_success`.
4. **數據隱私**: Traces 僅用於內部審計（internal-only），嚴禁導出為外部訓練集，且 `training_eligible=false`.
5. **門禁不繞過**: 雲端產出的補丁必須同樣通過 Verifier 測試門禁與 Compliance 門禁。

---

## 3. Compliance Checker 防禦規則升級
Compliance Checker 將在審計時執行以下硬性阻斷：
- 若 receipt 顯示使用了本機 14B，但 `resource_guard_passed` 為 `false` 或未記錄，判定為 **COMPLIANCE_FAIL**。
- 若 receipt 顯示 `cloud_api_used=true`，但未附帶 `owner_approval_token`，判定為 **COMPLIANCE_FAIL**。
- 雲端補丁若繞過 `verifier_status == "passed"`，直接判定為 **COMPLIANCE_FAIL**。
