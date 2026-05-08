# Nexus 認知演化長計劃 (v25.5) - 從學習閉環到自動演化

本文件定義了 Nexus 戰甲如何透過「雙學習系統」實現自我強化：一層提升 Nexus 路由策略，另一層為模型訓練提供高品質數據。

---

## 階段一：地基與數據採集 (P1–P3) [DONE]
*   **P1: 能力分類 Registry**：建立 9 類能力（偵查、修復、協作等）的語義標籤。
*   **P2: 學習軌跡合約 (Trace Contract)**：定義 `LearningExperience` 與 `CapabilityLifecycle`。
*   **P3: Runtime 數據採集器 (Harvester)**：在 `research_flow_service` 中接入，自動生成 Episode 紀錄。

## 階段二：策略學習與路由接入 (P4–P7) [PARTIAL]
*   **P4: Policy Learner 投影**：將 Episode 轉化為路由權重與 S2T 先驗。
*   **P5: CapabilityPlanner 接入**：讓路由能讀取過去成功配置（`learning_influenced=true`）。
*   **P6: S2T Selector 歷史先驗**：候選重排時參考歷史相似任務的勝率。
*   **P7: 升級策略 (Escalation Policy)**：學習何時自動從 Hyper 升級至 Nightshift 或 Swarm。

## 階段三：深度治理與分析 (P8–P10) [ACTIVE]
*   **P8: 策略分析服務 (Distillation)**：將失敗任務轉化為可審核的 Strategy Lesson。
*   **P9: 匯出門禁 (Export Gate)**：確保只有 REDACTED 且 GOLD 的軌跡能進入訓練集。
*   **P10: LearningSteward 五態治理**：實作 `DISCARD`, `FREEZE`, `SHADOW`, `PROMOTE`, `EXPORT` 的判定邏輯。

## 階段四：驗證、演化與生產門禁 (P11–P15) [PLANNED]
*   **P11: 自動化 Policy 晉升系統**：建立 shadow 到 promoted 的自動化門禁。
*   **P12: 軌跡故障挖掘 (Failure Miner)**：分析 `trust_mismatch` 案例，修正治理規則。
*   **P13: Autodata GOLD 篩選標準**：實作強弱分差 20% 的自動化判定。
*   **P14: 小型 Nexus Self-Test**：在內部實驗室跑失敗->學習->成功的完整閉環驗證。
*   **P15: Flash 2 題 A/B 測試門禁**：生產環境試點，證明 `tokens_per_success` 下降且無退步。

---

## 核心上線標準
1.  **解決率 (Solve Rate)**：不得低於 Baseline。
2.  **信心對位 (Trust)**：`trust_mismatch` 不得上升。
3.  **效率 (Efficiency)**：`tokens_per_success` 必須下降（路由變精準）。
4.  **安全 (Safety)**：所有的學習產出必須經過 `LearningSteward` 審計。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
