# Limited Assisted Adoption Dossier (Phase 6)

**Date**: 2026-06-15  
**Version**: v1.0.0  
**Status**: **READY FOR REVIEW / PROMOTION ELIGIBLE**  
**Governing spec**: [NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md](file://../roadmap/NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md)

---

## 1. 概述
本 Dossier 定義了 3B, 7B, 14B 模型在 Nexus 運行時 (Runtime) 的 **受限輔助掛載點 (Limited Assisted Mount Points)** 與安全防禦合約。所有掛載均只提供輔助決策 (Advisory)，嚴禁觸碰 L0 治理權威。

---

## 2. 申請掛載點與權限邊界 (Mount Points & Boundaries)

| Model Role | Applied Mount Point | Authority Level | Enforcement Mechanism |
| :--- | :--- | :--- | :--- |
| **3B Advisor** | strict-gated repair / route-review nodes | **Advisory Only** (No decision authority) | `NEXUS_S2T_3B_ASSISTED_MODE=low_risk` + Rust verifier validation |
| **7B Reasoner** | LocalDeliberationLane (Worker) | **Advisory Only** (No decision authority) | Selective triggering + 14B synthesis gate |
| **14B Synthesizer**| LocalDeliberationLane (Judge) | **Advisory Only** (No decision authority) | `is_mature_for_main_path` checks + shadow observations |

### 🚫 絕對紅線邊界 (Strict Red Lines)
1. **不得** 取代 L0 Runtime default router 或預設決策。
2. **不得** 取代 `receipt_verifier` 與 `hallucination_guard` (Verifier/Claim Gate)。
3. **絕對禁止** 模型自動修改或更新 Policy (例如 `promotion_allowed` 唯有通過 human-in-the-loop 才可修改)。

---

## 3. 運行時合約與防禦三道防線 (Three Lines of Defense)

所有模型掛載必須受到以下機制保護：

1. **第一道防線：Feature Flag & 物理隔離**:
   - `NEXUS_SHADOW_ADVISOR_ENABLED` 預設限制其決策為 shadow-only，不干擾主執行路徑。
2. **第二道防線：平滑退避 (Smooth Fallback)**:
   - 任何模型連線失敗、超時 (超過 500ms) 或輸出格式錯誤，核心直接退避至 Python/Rule-based baseline 實作，確保系統不崩潰。
3. **第三道防線：每列證據審計 (Per-row Evidence Logging)**:
   - 所有 shadow 決策與 baseline 決策對比均寫入 `.nexus/metrics/s2t_shadow_contract_evidence.jsonl`，定時審計 `trust_mismatch_rate` 與 `fallback_triggered` 率。

---

## 4. 驗收與簽收結論
經評估，本 limited assist 掛載策略與 Roadmap v3 治理原則 100% 對齊。3B 推薦模型、7B/14B 協商車道均已通過物理代價量化與回滾演練。本 Dossier 定性為 `READY_FOR_REVIEW`，準備提交 Limited Mount 審查。
