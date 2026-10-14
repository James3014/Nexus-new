# HANDOFF

更新：2026-10-14 · by Claude（workspace-fb）· base `4d6035ee2`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
#1889 第 2 步：PR #1890（probe evaluator ＋ GB-079 已覆蓋）合併後，另開 PR 把 GB-077 綁到 `gb077_live_gateway_identity`。原因：trusted Golden gate 用 base branch 的 evaluator 檢查 PR 的 corpus，evaluator 和綁定必須分兩次 PR（見 #1899）。

## 進行中
- #1889 / PR #1890：Golden 的 probe registry、GB-079 轉為已覆蓋（20 個 witness）、GB-077 實機 probe（先不綁定）。等檢查轉綠。
- #1216：V11 已開（step 6，Owner 說 "go"，2026-10-12）。屬研究觀察，不授予工程權限。
- #1757、#1758、#1760：invariant gap，仍 OPEN（PR #1768 已合併）。

## 待確認（沒有 Issue 號）
- （已解決 10/14）#29 實機 canary PASS 並經獨立審查，durable marker 成立、Issue 已關；#49 前提過時（World A 沒有任何出口回傳模型文字），依 Owner 決定以鎖定測試結案（PR #2161）。GB-078／GB-080 已轉為 covered。
- #1447（#526 relevance-aware convergence）是否保留，待 Owner。
- forecast_gate、LanceDB、MemPalace 接線已完成；MemPalace 的「禁止」belief 只顯示在 plan trace，selector 不會實際移除 skill。

## 卡住 / 注意
- Golden Behavior Corpus：100 個案例，98 個已覆蓋。剩下的 finding 是 GBF-002（live Gateway，只能實機驗）、GBF-007（#1750）。執行方式：`.venv/bin/python scripts/ops/run_golden_behavior_eval.py`。用 `scripts/ops/check_golden_finding_owners.py --strict` 檢查 finding 的 owner Issue 是否已經過期。
- live MCP Gateway：10/14 已 rebind 到 `f239b657`（#2036／#2037，GB-077 PASS）；現行授權 2026-10-14T09:40Z 到期。之後改為「從 main 自動部署＋冒煙測試＋自動退回＋獨立 venv」（#2153，workspace-64），期間不要手動 rebind。
- Issue 不再需要手寫 `NEXUS_CORE_EVIDENCE_UNIVERSE` marker：issue-gate 用 `evidence-universe: trusted-config`，證據範圍由 base ref 的 `.nexus-core/config.toml` 推導（nexus-core b245430b）。`NEXUS_CORE_MATERIAL_TRANSITION` 不變，改 material 身分時仍要。main 在開 PR 前後若有前進，Core gate 會回 `BASE_REF_NOT_ANCESTOR`，要 rebase（nexus-core#243）。
- 機密掃描涵蓋所有已發佈的 ref。測試 fixture 裡的權杖必須拆開寫（例如 `"xo" + "xb-"`），否則會擋住全 repo（#1898）。
- 工作模式檔有 fail-closed 驗證器 `scripts/ops/check_operating_mode.py`。YAML 新增欄位時要在同一個 PR 更新驗證器。
- AGENTS.md ≤ 12 KB；overlay 各有上限（task contract ≤ 36 KB）；task-class context ≤ 36 KB。這些上限透過 Golden GB-097 在每個 PR 檢查。
- 本機 `.venv` 要和 `uv.lock` 同步（`uv sync --frozen --all-groups --all-extras`），否則 Golden eval 會整批 collection 失敗。
- `nexus run` 只有在 delivery-gate receipt 同時符合 run_id 與目前 HEAD 時才是 VERIFIED（#1734），要設定 `NEXUS_RUN_ID=<task_id>`。
- Drone 成功路徑需要 localhost:11435 的 LLM。
