# HANDOFF

更新：2026-10-11 · by Claude · HEAD `de428f03d`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
- 合併 #1733 能力接線盤點的整合 PR（#1734、#1735、#1737、#1738、#1739、#1741、#1763 前 5 項），CI 全綠後依 Owner 指示直接合併。

## 進行中
- #1763：第 6-9 項（Belief v0.2、Swarm Go 部署包、Drone HUD、meta-opt preset 消費端）尚未處理。

## 待確認（沒有 Issue 號）
- forecast_gate 是 escalate_only executor：planner 選中它還需要 escalation trigger 才會真的執行，要接上需改 `nexus/services/capability_registry.py`。
- findings LanceDB：表的第一列沒有向量時不會建立 vector 欄位；5 個 LanceDB 根目錄尚未收斂。
- MemPalace `constraints_source` 尚未傳到 capability_constraints / prompt_builder。

## 卡住 / 注意
- `nexus run` 現在只有在 delivery-gate receipt 同時符合本次 run_id 與目前 HEAD 時才是 VERIFIED（#1734）。執行 delivery gate 時要設定 `NEXUS_RUN_ID=<task_id>`，否則一律 UNVERIFIED。
- `scripts/ops/ci_gate.py` 的 Ultra Review 步驟在只有 dry-run 時一律判定未驗證（#1763）。
