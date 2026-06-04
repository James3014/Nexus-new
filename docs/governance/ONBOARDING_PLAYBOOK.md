# Nexus v27 Domain Onboarding Playbook

本手冊定義了新題庫、新 Verifier Pack 與新治理策略接入 Nexus 平台的標準流程。

## 1. 接入準備 (Pre-flight)
- **Domain ID**: 定義唯一的領域識別碼（如 `pytorch_core`）。
- **Verifier Pack**: 實作對應領域的物理驗證規則。
- **Manifest**: 建立初步的任務清單，並標記為 `migration` 或 `challenge` 車道。

## 2. 規格准入 (Manifest Ingress)
所有新任務必須通過 `ManifestValidator` 檢查：
- `domain_id` 不得為空。
- 必須指定有效的 `promotion_policy`。
- `extension_metadata` 必須包含：
    - `target_recovery`: 目標回收率（預設 0.8）。
    - `risk_profile`: 棄權風險設定（conservative/balanced/aggressive）。

## 3. 車道演進路徑 (Lane Migration)
1. **Migration Lane**: 初始接入測試。重點在於驗證環境穩定性與 Verifier 覆蓋。
2. **Challenge Lane**: 攻堅期。透過 Feedback Loop 優化策略，直到達成 `target_recovery`。
3. **Promotion**: 提交 `PromotionReceipt`。若滿足 `Gain(C) > 0 && Loss(B) == 0`，則晉升至 **Baseline Lane**。

## 4. 治理收口 (Final Sealing)
- 更新 `DEEPSWE_FULL_LIBRARY_REPORT.md`。
- 產出 `SealedEvidence` 物理收據。
- 凍結該版本的 `manifest_hash`。

---
[NEXUS GOVERNANCE BOARD v27.0]
