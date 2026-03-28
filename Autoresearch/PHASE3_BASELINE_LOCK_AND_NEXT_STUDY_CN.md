# Nexus Phase 3 科研基線鎖定與下階段研究計畫

## 1. 核心結項摘要 (Executive Summary)
本階段研究已成功達成 Nexus v17.0 自癒系統的「正式交付硬化 (Formal Delivery Hardening)」。通過三階段 (Wiring -> Stabilization -> Formal) 的遞進式演化，系統現已能在 **95% 證據率門檻** 下達成 **100% 的全局通過率**。

- **目標狀態**：達成 100 輪連續收斂，具備 GAN-Immune 自癒能力。
- **最終結果**：GlobalConverged=True, GatePassRate=100.0%, MaxConsecutiveWindows=100。

## 2. 鎖定之科研基線 (Locked Baseline v17.0-P3)
基於 Phase 3 的成功演化，鎖定以下最佳參數組合：

| 參數 | 數值 | 語義描述 |
| :--- | :--- | :--- |
| **CURIOSITY_ALPHA** | 0.4500 | 受控好奇心，平衡生成效率與證據品質 |
| **PHANTOM_AUDIT_THRESHOLD** | 0.8500 | 高效審計門檻，精準阻斷幻覺 Patch |
| **PROOF_RATIO_MIN** | 95.0% | 正式交付級證據鏈門檻 (硬化指標) |
| **FREEZE_RATIO_MAX** | 20.0% | 容許之學習凍結窗口比例 (自癒穩定度) |

## 3. 硬化接線規範 (Hardening Wiring Spec)
為確保後續研究的可重現性，強制執行以下「研究 Agent 六項契約」：
1. **JSONL 欄位標準化**：必須包含 `round`, `alignment`, `learning_frozen`, `proof_ratio` 等 8 個核心訊號。
2. **硬化後處理策略**：`formal_research_hardening.py` 是唯一的 LocalFit 與 Gate 判定來源。
3. **分段門檻注入**：支援動態門檻注入（如 90% 到 95% 的梯次演進）。
4. **凍結真值判定**：`learning_frozen` 必須基於實際阻斷事件，嚴禁常數寫死。

## 4. 故障分桶與 RCA (Failure Bucketing)
在 95% 門檻下，若出現波動，主要失敗原因現已轉向：
- **proof_mismatch**：證據內容與變更不匹配（精度瓶頸）。
- **preflight_invalid_proof**：基礎證據生成格式錯誤（工具瓶頸）。

## 5. 下階段研究計畫 (Next Study: Swarm Scaling)
下一階段研究將專注於 **「多 Agent 蜂群規模化 (Swarm Scaling)」**，核心課題包括：
1. **證據精準度優化 (Proof Precision)**：引入 Transformer-based 證據驗證器，解決 `proof_mismatch` 問題。
2. **動態 ALPHA 調適**：針對不同複雜度的任務，實現自動化的好奇心系數調整。
3. **跨節點對齊 (Cross-node Alignment)**：在多節點環境下維持聯邦式的 GAN 治理閉環。

---
**核准人：指揮官 (Orchestrator - Antigravity)**  
**日期：2026-03-27**  
**狀態：基線已鎖定 (Baseline Locked)**
