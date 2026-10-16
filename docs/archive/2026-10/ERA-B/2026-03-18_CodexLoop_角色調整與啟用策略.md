# 2026-03-18 Codex-Loop 角色調整與啟用策略

## 決策
將 `codex-loop` 從主執行路徑降級為「條件式升級工具（fallback escalation）」。

## 背景
目前 Nexus 的主要提升來自：
1. Pipeline 模組化
2. CI Gate 與回歸測試硬化
3. 組件邊界清晰化

在此狀態下，常態 loop 並非必要，反而可能增加 token 成本與不確定性。

## 新執行策略
1. 預設模式：`One-shot`
- 所有一般任務先用 one-shot 路徑執行。

2. 升級條件（才啟用 codex-loop）
- 同任務連續 2 次審核失敗
- `review_status in {UNKNOWN, NOT_STARTED}`
- `repair_attempts > 2` 或 `phase_path` 重複卡在 R
- 高風險/高不確定任務（跨模組 + 外部依賴 + 高 drift）

3. 降級條件（返回 one-shot）
- 任務已達 gate
- loop 未帶來可量化提升（成功率/時間/成本）

## 自動觸發規則（先硬規則，後學習調參）
1. 硬規則（立即上線）
- `fail_streak >= 2` -> 觸發 loop
- `unknown_or_not_started = true` -> 觸發 loop
- `high_risk = true` 且 `one_shot_fail = true` -> 觸發 loop

2. 學習調參（第二階段）
- 以 `mode ROI` 自動調整觸發閾值。
- 若 loop 在最近 N 次無淨改善，提升觸發門檻或停用。
- 若 loop 在特定任務族群持續改善，降低該族群觸發門檻。

## 驗收指標
1. One-shot 路徑 success >= 95%
2. 啟用 loop 的任務占比 < 30%
3. loop 任務相對 one-shot 必須有淨改善（否則回退）
4. mode 相關欄位完整落盤：`execution_mode`, `trigger_reason`, `mode_roi`

## 實作注意
1. 在 orchestrator/repair phase 增加 `execution_mode` 欄位（one_shot|loop）。
2. 報表需區分不同模式的成效（成本、時間、成功率）。
3. 不可再把 loop 作為預設必經流程。
4. 增加 `trigger_reason`（例如 `fail_streak`, `unknown_status`, `high_risk`）便於審計。
