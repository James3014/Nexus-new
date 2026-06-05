# Nexus 計劃 vs 代碼現況核對（2026-04-28）

## 結論
你感覺是對的：我上一版計劃裡有幾項其實 Nexus 已經有「部分或完整」實作，不該當成全新功能。

---

## A. 已有（可直接沿用）

1) 單一 owner 任務模型（已有）
- 證據：`nexus/orchestrator/task_contract.py` 行 106-113（`owner`, `evidence_requirements`）
- 證據：`scripts/engine/nexus_cli.py` 行 2695-2711（`multi-agent create-task --owner`）

2) 任務狀態機與 blocked/failed/rejected（已有）
- 證據：`nexus/orchestrator/task_contract.py` 行 6-31（狀態與合法轉移）

3) 驗收證據鏈與 evidence_bundle（已有）
- 證據：`nexus/delivery/evidence_verifier.py`（schema 驗證、anti-drift、replay）
- 證據：`scripts/engine/nexus_cli.py` 多處 `_write_hallucination_evidence`、`_enforce_hallucination_gate`

4) fail-closed / gate 阻斷（已有）
- 證據：`nexus/delivery/evidence_verifier.py` 行 92-98（internal error 直接 LOW）
- 證據：`nexus/services/policy_gate.py` 行 59-68（health < 0.3 直接 BLOCK）

5) 高風險需人工核准字樣檢查（已有）
- 證據：`scripts/engine/l6_gate.py` 行 60-69（若高風險未含 `requires human approval` 則拋錯）

6) Multi-agent 任務流程命令（已有）
- 證據：`scripts/engine/nexus_cli.py` 行 2683+（init/create-task/start/status/verify/close/integrate/audit/submit）

---

## B. 部分有（需補齊契約）

1) Proposal/ADR Gate（部分）
- 現況：有 proposal 相關程式與文件痕跡，但沒有統一成你要的「跨邊界必經 proposal card/ADR gate」硬性流程。
- 證據：`nexus/core/project_planner.py`（proposal）、`scripts/ops/review_proposal.py`。
- 缺口：缺一致 CLI gate 與 fail-closed 判定點。

2) Acceptance Matrix 輸出格式（部分）
- 現況：有 evidence verifier 與 submission gate，但「固定四欄矩陣格式」未看到全域標準化輸出。
- 證據：`nexus/delivery/evidence_verifier.py`、`nexus/delivery/submission.py`。

3) 8 小時自治模板（部分）
- 現況：有任務狀態與 verify/submit，但時間盒、stop-loss、中斷規則還是以 skill/流程規範為主，非單一內建契約。

---

## C. 目前看起來尚未內建（或僅在我們計劃/報告層）

1) consulted_agents 上限 2 的硬性 enforcement（未見代碼 enforcement）
- 現況：文件有寫，但代碼未檢到 `consulted_agents` 模型約束。

2) delivery_profile（mock_only/live_browser/live_api）內建欄位與 gate（未見核心代碼）
- 現況：主要出現在我們新增報告/skill；代碼層未見一致欄位與驗證流程。

3) 問題正規化（question normalization + source anchoring）作為 ask 前置內建模組（未見核心流程）
- 現況：本輪是用回放清單層手動修補，不是 nexus ask 內建前處理。

---

## D. 對原計劃的修正建議

把上一版「全新建置」改為「增量整合」：

- P0（先做）：把已存在能力串成單一路徑（multi-agent -> verify -> submission -> evidence gate）
- P1（補缺）：加 `consulted_agents <= 2`、`delivery_profile` schema、高風險 human-approval 一致驗證
- P2（優化）：ask 前置正規化與重排規則，避免 notice/table claim 影響回答

---

## E. 給其他 Agent 的接手重點

1) 先不要重做已有的 evidence/gate/status/owner 模組。
2) 先從「缺口補齊」下手：consulted_agents、delivery_profile、proposal/ADR 硬 gate。
3) 全部改動都走 fail-closed：沒證據就 RETURN/BLOCK，不得宣告 PASS。
