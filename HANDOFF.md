# HANDOFF

更新：2026-10-11 · by Claude · HEAD `ba1cc6a71`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
#1773 讓 PR #1774（activation push 以 `gh variable delete` 套用空值、readback 視缺席為 `""`）通過檢查並落地——依據：V11 host run 停在 runbook step 3（manifest push exit 3），直接阻塞 #1216 的 activation；Owner 已核准 option b。

## 進行中
- #1773 / PR #1774：修正已提出，待檢查轉綠後合併。
- #1216：V11（`AGY_GEMINI_3_8_FLASH_MEDIUM_V11`）step 0–2 通過、凍結 SHA `895e5388`，等 #1773 修好後從 step 3 續跑。
- #1757、#1758、#1760 等 invariant gap / PR #1768：2026-10-11 invariant 覆蓋稽核的修正，檢查進行中。
- #1763：第 6–9 項（Belief v0.2、Swarm Go 部署包、Drone HUD、meta-opt preset 消費端）尚未處理。

## 待確認（沒有 Issue 號）
- #1733 的整合 PR #1767 已合併，但 issue #1733 仍 open；#1580 的 PR #1775 已合併，issue 仍 open——各自跑 `nexus-certify issue-check` 後再關。
- forecast_gate 是 escalate_only executor：planner 選中它還需要 escalation trigger 才會真的執行，要接上需改 `nexus/services/capability_registry.py`。
- findings LanceDB：表的第一列沒有向量時不會建立 vector 欄位；5 個 LanceDB 根目錄尚未收斂。
- MemPalace `constraints_source` 尚未傳到 capability_constraints / prompt_builder。
- 舊 open PR 長期無活動（如 #1437、#1447；#1583 與 #1584 head 是同一個 SHA），是否關閉待 Owner 決定。

## 卡住 / 注意
- `nexus run` 現在只有在 delivery-gate receipt 同時符合本次 run_id 與目前 HEAD 時才是 VERIFIED（#1734）。執行 delivery gate 時要設定 `NEXUS_RUN_ID=<task_id>`，否則一律 UNVERIFIED。
- `scripts/ops/ci_gate.py` 的 Ultra Review 步驟在只有 dry-run 時一律判定未驗證（#1763）。
- 「Trusted verifier (default branch)」曾在暫存目錄清理時 race（`commit-graphs` not empty）；修正 PR 在 `claude/fix-verifier-cleanup-race`。
- #1216 是研究觀察（`RESEARCH_OBSERVATION_ONLY`），不授予工程權限。
