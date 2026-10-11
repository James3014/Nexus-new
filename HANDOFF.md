# HANDOFF

更新：2026-10-11 · by Claude · HEAD `d8d7a842f`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
#1773 讓 PR #1774（activation push 以 `gh variable delete` 套用空值、readback 視缺席為 `""`）通過檢查並落地——依據：V11 host run 停在 runbook step 3（manifest push exit 3），直接阻塞 #1216 的 activation；Owner 已核准 option b。

## 進行中
- #1773 / PR #1774：修正已提出，待檢查轉綠後合併。
- #1216：V11（`AGY_GEMINI_3_8_FLASH_MEDIUM_V11`）step 0–2 通過、凍結 SHA `895e5388`，等 #1773 修好後從 step 3 續跑。
- #1757、#1758、#1760 等 invariant gap / PR #1768：2026-10-11 invariant 覆蓋稽核的修正，檢查進行中。

## 待確認（沒有 Issue 號）
- #1733 已關閉（以 CI issue completion 證據；nexus-certify issue-init 因 EVIDENCE_UNIVERSE_STALE 無法使用）；#1580 需獨立 reviewer 與合併後 workflow 證據，留給 Owner。
- forecast_gate、LanceDB、MemPalace 接線已完成：forecast_gate 在 run_mainchain 端到端執行且 receipt 保留 `trigger_source`（位於 `capability_results.forecast_gate.response`）；LanceDB 根目錄改用 `nexus/services/lancedb_roots.py`（guard test 防回退；`nexus/infrastructure/storage_implementations.py` 因分層規則保留字面路徑）；舊表自動補 tenant_id/drawer_id/aaak_content。
- MemPalace：同一 skill 在同類任務連續失敗 3 次（`NEXUS_BELIEF_FORBID_STREAK`）會寫入「禁止」belief，成功即解除；目前只顯示在 plan trace / prompt，selector 不會實際移除被禁止的 skill（要強制需另改路由）。
- #1447（#526 relevance-aware convergence）是否保留待 Owner；#1437、#1583 已關閉。

## 卡住 / 注意
- `nexus run` 現在只有在 delivery-gate receipt 同時符合本次 run_id 與目前 HEAD 時才是 VERIFIED（#1734）。執行 delivery gate 時要設定 `NEXUS_RUN_ID=<task_id>`，否則一律 UNVERIFIED。
- `scripts/ops/ci_gate.py` 的 Ultra Review 步驟在只有 dry-run 時一律判定未驗證（#1763）。
- 「Trusted verifier (default branch)」曾在暫存目錄清理時 race（`commit-graphs` not empty）；修正 PR 在 `claude/fix-verifier-cleanup-race`。
- Drone 成功路徑需要 localhost:11435 的 LLM；`nexus drone run` 在 LLM 不可用時記 FAIL 並 exit 1。
- #1216 是研究觀察（`RESEARCH_OBSERVATION_ONLY`），不授予工程權限。
