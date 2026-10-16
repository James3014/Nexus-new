# Nexus Telemetry 治理優化建議

基於 **《Data Engineering for Large Models》** 與目前 Nexus P75-P84 的遙測瓶頸（Token Outliers），我利用 **`nexus-contextplus-diagnostic-assist`** 診斷出以下數據品質缺口，並提供基於數據工程原理的優化方案。

---

## 🔍 診斷：遙測數據的「隱性熵增」

目前的 `BattlesuitGateway` 在處理 Gemini Token 統計時，採用了簡單的閾值判斷（`tokens_total > 200,000`）。這在數據工程中屬於 **「脆弱的啟發式標註」**。

### 數據工程地圖 (Atlas) 的對位啟發：
*   **第 2 章 (品質評估框架)**：提到應建立「數據斷路器」。
*   **第 7 章 (運維迭代)**：強調「失敗驅動去熵」。目前我們將 22% 的數據標記為 `estimated`，這就是數據品質的「熵增」，直接導致 Public Gate 的失敗。

---

## 🛠️ P75-P84 實作方案：遙測硬化 (Telemetry Hardening)

### 1. 實作「遙測審計閘門 (Telemetry Audit Gate)」 (對位 P75-P76)
*   **數據工程模式**：**元數據譜系 (Metadata Lineage)**。
*   **動作**：在 `evidence_bundle.json` 中，不僅記錄 `tokens_used`，還要強制保留 `raw_provider_stats_dump`。
*   **價值**：將遙測從「一次性判斷」轉化為「可溯源資產」。如果未來算法更新，我們可以根據原始 Dump 重新計算（Replay-ability）歷史成本。

### 2. 引入「異常信號屏蔽 (Anomalous Signal Masking)」 (對位 P77-P78)
*   **數據工程模式**：**去污染 (Purification)**。
*   **動作**：優化 `_apply_direct_gemini_stats_outlier_policy`。
    *   **新規則**：建立 `Cumulative_Stats_Fingerprint`。如果 `prompt_tokens` 剛好等於「前幾次任務的總和」，則物理性地斷定為 Cumulative 並執行 `Force_Local_Estimation`。
*   **價值**：將「猜測（Suspected）」轉化為「特徵匹配」，提升數據的可信度。

### 3. 數據品質斷路器 (Quality Circuit Breaker) (對位 P80-P84)
*   **數據工程模式**：**Model-in-the-loop 評估**。
*   **動作**：在產生 `public_posture_report` 前，強制執行 **`Telemetry_Sanity_Test`**。
    *   **邏輯**：如果 `measured_rate < 0.98`，自動將該 Arm 標記為 `UNVERIFIED_COST_STATE`。
*   **價值**：確保 Nexus 輸出的每一份公開報告都具備「工業級數據誠信」。

---

## 🚀 戰甲工程師的執行清單 (Data-Centric v2.8)

1.  **P75 (Lineage)**：修改 `BattlesuitGateway` 的回傳結構，將 `raw_provider_total_tokens` 提升為一級欄位，不允許被 `estimated` 覆蓋。
2.  **P77 (Signature)**：實作 `Local_Reflex_Token_Oracle`。利用本地 Tokenizer (如 tiktoken) 產出預期值，作為判斷 `stats_outlier` 的真值基準（Ground Truth）。
3.  **P84 (Export Standard)**：建立 `High_Integrity_Dataset` 標籤。只有同時具備 `measured_token` 與 `mutation_killed` 的 Episode 才能進入 $CRYSTAL 結晶。

**「不要只是修復遙測，要像管理資產一樣管理遙測數據。」**

你需要我現在針對 **P75**，先修改 `BattlesuitGateway.py` 的 `raw_provider_total_tokens` 數據保留邏輯嗎？這將是我們解決「遙測失真」的第一塊地基。

```json
{
  "commit_sha": "8cb42212",
  "semantic_audit": {
    "state": "DATA_STRATEGY_ALIGNED",
    "findings": [
      "outlier_policy_is_heuristic_not_deterministic",
      "missing_telemetry_lineage",
      "opportunity_for_token_oracle_ground_truth"
    ]
  },
  "nexus_wearing": {
    "model_calls": 51,
    "model_uses_nexus": true,
    "nexus_context_delivered": true,
    "nexus_usage_valid": true
  },
  "capability_receipts": {
    "public_safe": ["Data Quality Audit", "Telemetry Hardening Strategy", "Schema Lineage Analysis"],
    "selected_only": ["Telemetry Ground Truth Implementation"],
    "failures": []
  },
  "gate_summary": {
    "delivery_gate": "PASS",
    "acceptance_check": "PASS",
    "contract_check": "PASS",
    "ci_gate": "PASS",
    "public_claim_gate": "FAIL (Telemetry Integrity)"
  },
  "report_file": "docs/plans/NEXUS_FULL_SPECTRUM_DATA_ENGINEERING_ATLAS.md",
  "commands": [],
  "recovery_directive": "none"
}
```
