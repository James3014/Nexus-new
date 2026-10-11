# HANDOFF

更新：2026-10-11 · by Claude · HEAD `1d941138a`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
- 合併 #1763 第 6-9 項的 PR（Belief v0.2、Swarm 部署路徑、Drone HUD、meta-opt preset 消費端），CI 全綠後依 Owner 指示直接合併。

## 進行中

## 待確認（沒有 Issue 號）
- `nexus_swarm/cmd/swarm-manager` 舊 demo 用到已移除的 proto 欄位，目前以 build tag `legacy_v18_demo` 排除；要重寫還是退役待決定（README 與 scripts/test_local_swarm.sh 仍指向它）。
- meta-opt preset 只套用到 research:auto-flow 的 timeout/ratio/history 設定；ab_trials、max_wall_time_sec 與 Nightshift budget 是否也要吃 preset 待決定。
- Belief v0.2：edge 方向採 belief→artifact、depends_on 觸發失效；反向傳播、版本歷史、接入路由未做；`.nexusknowledge/beliefs.jsonl` 既有重複資料未清理。
- forecast_gate 是 escalate_only executor：planner 選中它還需要 escalation trigger 才會真的執行。
- findings LanceDB：表的第一列沒有向量時不會建立 vector 欄位；5 個 LanceDB 根目錄尚未收斂。
- MemPalace `constraints_source` 尚未傳到 capability_constraints / prompt_builder。

## 卡住 / 注意
- `nexus run` 只有在 delivery-gate receipt 同時符合本次 run_id 與目前 HEAD 時才是 VERIFIED（#1734）。執行 delivery gate 時要設定 `NEXUS_RUN_ID=<task_id>`。
- `scripts/ops/ci_gate.py` 的 Ultra Review 步驟在只有 dry-run 時一律判定未驗證（#1763）。
- Drone 的成功路徑需要 localhost:11435 的 LLM；本環境只驗證了失敗即 FAIL 的路徑。
