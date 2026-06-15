# Limited Assisted Adoption Dossier (Phase 6)

**Date**: 2026-06-15  
**Version**: v1.0.1  
**Status**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**  
**Governing spec**: [NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md](file://../roadmap/NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md)

---

## 1. 概述
本 Dossier 定義了 1.5B, 3B, 7B, 14B 模型在 Nexus 運行時 (Runtime) 的 **受限輔助掛載點 (Limited Assisted Mount Points)** 與安全防禦合約。所有掛載均只提供輔助決策 (Advisory)，嚴禁觸碰 L0 治理權威。

---

## 2. 申請掛載點與權限邊界 (Mount Points & Boundaries)

### 📌 模型掛載規則 (Mounting Rules)
1. **3B Advisor = limited assist only**: 僅在輔助（Advisory）模式下運作，無 runtime 決策權，且只限於 shadow-first/strict-gated 場景。
2. **1.5B Gatekeeper = optional front-door hint**: 作為非阻塞、可選的前置篩選層。只要 telemetry 顯示其在 short-task 的延遲（latency）或成本（cost）優勢不再成立，必須隨時退避回退（rollback-ready）。
3. **7B/14B Deliberation = specific task families only**: 嚴格限制僅能在特定任務的白名單內啟動，絕不可泛化為 default path。
   - **允許任務白名單 (Deliberation Whitelist)**:
     - `high-uncertainty` (高不確定性任務)
     - `repair-review` (修復評估任務)
     - `research-brief` (研究簡報與分析任務)

| Model Role | Applied Mount Point | Authority Level | Enforcement Mechanism |
| :--- | :--- | :--- | :--- |
| **1.5B Gatekeeper**| Optional front-door screening | **Advisory Only** | Optional non-blocking bypass + rollback to default rules |
| **3B Advisor** | strict-gated repair / route-review nodes | **Advisory Only** (No decision authority) | `NEXUS_S2T_3B_ASSISTED_MODE=low_risk` + Rust verifier validation |
| **7B Reasoner** | LocalDeliberationLane (Worker) | **Advisory Only** (No decision authority) | Selective triggering + 14B synthesis gate |
| **14B Synthesizer**| LocalDeliberationLane (Judge) | **Advisory Only** (No decision authority) | `is_mature_for_main_path` checks + shadow observations |

### 🚫 絕對紅線邊界 (Strict Red Lines)
1. **嚴禁取代 default router**: 不得將任何模型（含 1.5B, 3B, 7B, 14B）升級或替換為預設的 L0 Runtime default router。
2. **嚴禁取代 verifier / claim gate / delivery gate**: 不得取代核心的 `receipt_verifier`、`hallucination_guard`、`delivery_gate` 等 L0 安全與核銷機制。
3. **嚴禁自動 policy mutation**: 絕對禁止模型自主修改、更新或發佈任何安全策略與路由配置（如 `promotion_allowed` 等策略變更，僅能通過 Human-in-the-loop 人工審查與簽署）。
4. **必須具備 fallback/feature flag/rollback 機制**: 所有的模型掛載必須保留 feature flag 物理開關，若模型失效必須能在毫秒級內無縫退避（fallback）至 rule-based 靜態策略。

---

## 3. 運行時合約與防禦三道防線 (Three Lines of Defense)

所有模型掛載必須受到以下機制保護：

1. **第一道防線：Feature Flag & 物理隔離**:
   - `NEXUS_SHADOW_ADVISOR_ENABLED` 預設限制其決策為 shadow-only，不干擾主執行路徑。
2. **第二道防線：平滑退避 (Smooth Fallback)**:
   - 任何模型連線失敗、超時 (超過 500ms) 或輸出格式錯誤，核心直接退避至 Python/Rule-based baseline 實作，確保系統不崩潰。
3. **第三道防線：每列證據審計 (Per-row Evidence Logging)**:
   - 所有 shadow 決策與 baseline 決策對比均記錄至 `.nexus/metrics/s2t_shadow_contract_evidence.jsonl`，定時審計 `trust_mismatch_rate` 與 `fallback_triggered` 率。

---

## 4. 驗收與簽收結論
經評估，本 limited assist 掛載策略與 Roadmap v3 治理原則 100% 對齊。3B 推薦模型、7B/14B 協商車道均已通過物理代價量化與回滾演練。本 Dossier 判定口徑為：
`Eligible for limited assisted adoption review; not eligible for default-path promotion.`
