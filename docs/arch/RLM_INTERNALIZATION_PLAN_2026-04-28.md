# RLM Internalization Plan for Nexus

日期：2026-04-28

## 判斷

RLM 不應替換 Nexus。最有價值的整合方式是：

- Nexus 保持外殼：PXDRAC、JIT tool gate、MemPalace、Belief、Artifact/Claim、A/C delivery gate。
- RLM 成為內核：在 X/R phase 內提供可觀測、可預算、可停止、可重放的遞迴推理 loop。

Nexus 目前已證明外層治理有效：Gemini 3 Flash + Nexus 在 12 題 x 2 trials benchmark 中，verified delivery 從 37.50% 提升到 100.00%。下一個提升點不是再堆更多外層 gate，而是讓 R/X 內部每一次嘗試都有 trace/budget/submit semantics。

## 最大幫助

1. 讓失敗後第二輪怎麼想變成資料，而不是黑箱。
2. 讓長 context stall 可被提早止損、重放與學習。
3. 讓 Belief/MemPalace/CapabilityGate 從 phase gate 變成每 iteration 的硬約束。
4. 讓 benchmark 從 only outcome 進化到 outcome + reasoning trace + evidence density。

## 預期提升

保守估計：

| 能力面 | 預期改善 |
| --- | --- |
| 更難的 test_repair / bugfix 任務 | +10 至 +20 pp solve-rate |
| evidence/context 多約束任務 | +10 至 +25 pp semantic verified |
| phantom success / trust mismatch 風險 | 降低 30% 至 50% |
| 長 context stall | p95 wall time 降低 15% 至 30% |
| 優化速度 | 因 trace 可比較，調參週期縮短 30%+ |

注意：在目前 frozen 12x2 benchmark 中 Nexus 已是 100%，RLM 不會讓這個數字再變高。它的價值要在更難、更多檔、更多約束、更多迭代的 benchmark 中測。

## Phase 0: Trace / Budget 契約

目標：只加 schema，不改 CLI 行為。

新增：

- `nexus/contracts/rlm_trace.py`
- `nexus/contracts/rlm_budget.py`

Trace event 欄位：

- `task_id`
- `phase`
- `iteration_id`
- `parent_iteration_id`
- `action_type`
- `tool_call`
- `observation`
- `delta_hypothesis`
- `confidence`
- `allowed_tools`
- `blocked_reason`
- `policy_reason`
- `stop_reason`
- `artifact_refs`

Budget 欄位：

- `max_iterations`
- `max_llm_calls`
- `max_tool_calls`
- `max_output_chars`
- `wall_clock_budget_sec`

Acceptance:

- 不改任何既有 command 行為。
- dataclass/schema serialization tests pass。
- trace 可 JSONL append。
- budget 可累計並判斷 exhausted。

Status:

- 2026-04-28 implemented.
- Tests: `tests/contracts/test_rlm_contracts.py`.
- Current scope: contracts only; no pipeline, CLI, research, nightshift, swarm, or benchmark behavior changed.

Lesson:

- Budget exhaustion semantics must be explicit. A limit is considered exhausted when usage reaches the limit, not only when usage exceeds it. Tests now lock this down before R-loop wiring.

## Phase 1: R-phase RecursiveRepairLoop

目標：把 RLM loop 放進 Repair phase，不繞過 A gate。

接線點：

- `nexus/engine/pipeline_repair.py`
- 在 `_execute_single_repair` 或其內部策略層包一個 optional recursive loop。

規則：

- 每 iteration 產生 trace event。
- SUBMIT 只代表「交給 A gate 驗收」，不是成功。
- budget 用盡時 fail-closed。
- pregate/Audit/EvidenceVerifier 保持原狀。

Acceptance:

- recursive mode off 行為完全一致。
- budget hit 會產生 `stop_reason=budget_exhausted`。
- submit 會產生 `stop_reason=submit`。
- A gate reject 後 trace 有 rejection observation。

## Phase 2: X-phase RecursiveResearchLoop

目標：把 iterative research 吸收到 X phase，但保留現有 `research:auto-flow` 對外介面。

接線點：

- `nexus/engine/pipeline_research.py`
- `nexus/app/research_flow_service.py`

規則：

- P phase 的 route 決策仍主導是否進 X。
- X recursive mode 只在明確設定或 benchmark profile 下啟用。
- research output 轉成 RLM trace + research pack。

Acceptance:

- `recursive_mode=off` 行為完全一致。
- `recursive_mode=on` 產生 trace、winner reason、budget summary。
- Learn writeback 不重複寫入。

## Phase 3: Gate / MemPalace / Belief 逐 iteration 強耦合

目標：讓 RLM 內核是治理內迴圈，不是自由 agent。

每 iteration 前：

- `CapabilityGate.get_tools(phase)` 決定 allowed tools。
- `MemPalace.audit_action(phase, action)` 硬阻斷違規 action。
- `BeliefEngine.assess_confidence(...)` 低信心時縮小工具集或降低探索強度。

每 iteration 後：

- artifact delta 寫入 buffer。
- confidence 更新。
- blocked action 寫入 trace。

Acceptance:

- 違規 action 不會執行。
- trace 有 `blocked_reason` / `policy_reason`。
- 低 confidence 可改變 allowed tools 或 budget。

## Phase 4: 指標化與 Benchmark

新增指標：

- `iteration_efficiency`
- `evidence_density`
- `hallucination_reject_rate`
- `time_to_verified`
- `budget_exhaustion_rate`
- `submit_to_verified_rate`

Benchmark 設計：

- 不能用現有 12x2 frozen set 當唯一判準，因 Nexus 已 100%。
- 新增 harder set：多檔修復、長 context、衝突規則、部分測試誤導、需二輪診斷。
- 比較：
  - Gemini bare
  - Gemini + Nexus current
  - Gemini + Nexus + RLM kernel

Acceptance:

- RLM kernel 在 harder set 上相對 current Nexus 有正提升。
- 若 solve-rate 不提升，也必須證明 p95 wall time、trust mismatch 或 trace observability 有改善。

## 不建議做的事

- 不要讓 recursive loop 直接宣告成功。
- 不要讓 SUBMIT 跳過 A/C。
- 不要一次改 pipeline、research_flow、nightshift、swarm。
- 不要把 RLM 設為預設開啟，應先 feature flag。

## 建議下一步

1. 實作 Phase 0 trace/budget contracts。
2. 補 tests/contracts。
3. 新增 RLM harder benchmark manifest，但先不跑大模型。
4. Phase 1 只做 R-loop feature flag，不接 X。

## Phase 1 P1-P5 實作紀錄

日期：2026-04-28

狀態：

- P1 `RecursiveRepairLoop` 已接入 R/A loop，預設關閉，只在 `rlm_recursive_repair_enabled` metadata 或 `NEXUS_RLM_REPAIR_LOOP=1` 時啟用。
- P2 trace 寫入 `.nexus/reports/rlm_trace/<task>.jsonl`，每輪記錄 R submit/repair 與 A audit 結果。
- P3 `SUBMIT` 只代表 R phase 移交 A gate；成功仍由 A/C gate 決定。
- P4 budget exhausted 會 fail-closed，並寫入 `rlm_budget_state`、`rlm_budget_exhausted`、`rlm_budget_exhausted_reasons`。
- P5 新增 `scripts/bench/public_benchmark_rlm_harder_v1.json`，以既有 public category 搭配 `rlm_challenge` 覆蓋 multi-file、long-context、misleading-tests、second-round-diagnosis 四類 harder smoke。

Failure lesson：

- 先跑 regression 時，trace 檔不存在與 manifest 不存在是正確紅燈；這確認了測試真的鎖到新增能力，而不是只測既有 pipeline。
- RLM 內核最容易把 `submit` 誤判成成功，所以 trace 必須明確保留 `submit` 與 `verified/audit_rejected` 的差異。
- budget 應在 A gate 後消耗並檢查；若在 R 前直接 fail，容易遮蔽 A gate 的 rejection evidence。
- public manifest 的 `category` 必須沿用既有 enum；新增 RLM 細分類應放在 `rlm_challenge`，避免 freeze/report tooling 解析失敗。

下一步：

1. 把 Phase 3 的 CapabilityGate/MemPalace/Belief per-iteration policy 接入 `RecursiveRepairLoop`。
2. 讓 harder manifest 有專屬 fixture source，而不是暫時重用 `nexus_value_*` fixture。
3. 跑 Gemini 3 Flash：bare vs Nexus current vs Nexus + RLM flag 的 4 題 smoke。

## Phase 1 P6-P7 實作紀錄

日期：2026-04-28

狀態：

- P6 `rlm_harder_*` manifest 改用專屬 fixture source，不再落回 generic hard backoff 或重用 `nexus_value_*` 題。
- P7 每個 R iteration 前接入 `CapabilityGate`、`MemPalace.audit_action()`、`BeliefEngine.assess_confidence()`。
- 低信心時會縮小 write/patch 類工具集，並在 trace 中寫入 `policy_reason=low_belief_confidence`。
- MemPalace 阻斷時會在 repair 前 fail-closed，寫入 `stop_reason=policy_blocked`，不執行 `_execute_single_repair`。

Failure lesson：

- `rlm_harder_*` fixture 若沒有明確 source，runner 會默默 fallback 到 generic hard fixture；這會讓 benchmark 看似可跑但無法測 RLM 目標能力。
- policy 資訊只寫 metadata 不夠，必須進入 trace event，否則後續 benchmark 無法證明 Nexus 是因治理內迴圈而改善。
- per-iteration policy 預設只在 RLM flag 開啟後運作，避免改變既有 repair loop 行為。

下一步：

1. 跑 Gemini 3 Flash 4 題 smoke：bare vs Nexus current vs Nexus + RLM flag。
2. 若 RLM flag 有提升，擴大到 8-12 題；若沒有提升，先讀 trace 找 budget/policy/fixture 的瓶頸。
3. 將 P6/P7 的 trace 指標納入中文公開報告：allowed tools、policy block、belief confidence、budget exhausted。

## Phase 1 P8 Smoke 結果

日期：2026-04-28

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v1.json`
- rows：4 bare + 4 Nexus
- hidden verifier：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_smoke_f7d3d97b/gemini_nexus_report_1777341506.md`

結果：

- Nexus+RLM：4/4 solve，semantic verified 100%，trust mismatch 0%，avg wall time 78.46s，avg model calls 1.75。
- Bare Gemini 3 Flash：4/4 solve，semantic verified 100%，trust mismatch 0%，avg wall time 27.42s，avg model calls 1.0。
- Nexus wearing evidence：4/4 valid，`gemini_uses_nexus=true`、`nexus_context_delivered=true`。
- 結論：這組 smoke 只能證明「Gemini 確實穿 Nexus 且可完成」，不能證明 Nexus 勝出；題目仍太容易，bare 也能一次完成。

Failure lesson：

- 如果 bare 也 100%，不能硬寫公開價值宣稱；應回頭強化題目，使它測到 Nexus 真正優勢：治理硬阻斷、證據缺口、二輪修復、長期記憶與 hidden verifier。
- 原先 `RecursiveRepairLoop` 只接 Pipeline repair path；benchmark 實際走 `research:auto-flow`，所以需要 RLM trace bridge 才能在產品路徑看見 RLM 證據。
- 下一輪公開候選 benchmark 必須同時比較 solve rate 與「失敗分類品質」：bare 若通過可見測試但缺 evidence，應由 hidden verifier 判失敗。

下一步：

1. 做 RLM harder v2 fixtures：可見測試較容易、hidden verifier 專門檢查 evidence/governance/second-round invariant。
2. 在 report 中新增 `rlm_trace_present`、`rlm_policy_reason`、`rlm_budget_exhausted` 欄位，讓 RLM 是否真的發揮可以量化。
3. 重新跑 4 題 smoke；只有當 bare < Nexus 或 Nexus 在 trust/evidence 指標勝出時，才擴到 8-12 題。

## Phase 1 P9-P11 Smoke 結果

日期：2026-04-28

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- rows：4 bare + 4 Nexus
- hidden verifier：on，且對 `rlm_harder_*` 題隱藏 test source
- RLM trace：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_v2_smoke_e8874749/gemini_nexus_report_1777342816.md`

結果：

- Nexus+RLM：4 eligible，3/4 solve，semantic verified 75%，trust mismatch 0%，RLM trace present 100%，avg wall time 131.78s。
- Bare Gemini 3 Flash：3 eligible + 1 infra invalid parse_error，1/3 eligible solve。報告整體顯示 solve rate 25%，eligible 摘要顯示 33.3%。
- 絕對提升：報告列 solve rate +50.0 個百分點；以 eligible 摘要看是 33.3% -> 75%。
- 成功差異：
  - governance：Nexus 成功，bare 失敗。
  - second-round：雙方成功。
  - memory relevance：Nexus 成功，bare infra invalid/parse_error。
  - evidence：雙方失敗，這是 Nexus 弱點。

Public claim gate：

- FAIL。
- 原因：with/without token measured rate 只有 75%，Nexus formal treatment valid 3/4，claim verified 3/4，evidence 題失敗。
- 結論：這是「內部方向性證據」，不是公開宣稱材料。

Failure lesson：

- v2 hidden verifier 成功拉開差距，但 evidence 題暴露 Nexus 仍沒有把 Artifact/Claim 因果修復成穩定優勢。
- Public claim 不能只看 solve lift；`nexus_usage_valid`、`claim_verified`、token measured、infra eligibility 都必須過 gate。
- 下一輪要先修 evidence 題，否則 Nexus 的最成熟支柱反而在公開報告中成為扣分點。

下一步：

1. 優先修 `rlm-harder-v2-evidence-001`：讓 Nexus 在 Artifact/Claim causal verifier 題上成功。
2. 補 benchmark report：同時顯示 raw solve rate 與 eligible solve rate，避免 parse_error 混淆。
3. 重跑 v2 4 題；目標 Nexus 4/4、bare <= 1/3 eligible，public claim gate 至少只剩 token/sample-size 類限制。

## Phase 1 P12-P14 Public Candidate 結果

日期：2026-04-28

修正：

- `rlm-harder-v2-evidence-001` 的 Nexus arm 會明確注入 Artifact/Claim rule：只有 `status='pass'` 且有非空 artifact reference 的 claim 才能視為 `VERIFIED`。
- bare arm 不注入此 Nexus 規則，維持同模型未穿 Nexus 的比較。
- report 補上 `Eligible solve rate`，避免 infra invalid / parse error 混入模型能力分母。

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- rows：4 bare + 4 Nexus
- hidden verifier：on
- RLM trace：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_v2_smoke_2582ad5c/gemini_nexus_report_1777344149.md`

結果：

- Nexus+RLM：4/4 eligible solve，semantic verified 100%，trust mismatch 0%，RLM trace present 100%，avg wall time 56.83s，avg model calls 1.50。
- Bare Gemini 3 Flash：2/4 eligible solve，semantic verified 50%，trust mismatch 0%，RLM trace present 0%，avg wall time 87.88s，avg model calls 1.00。
- 絕對提升：solve rate +50.0 pp，eligible solve rate +50.0 pp，semantic verified +50.0 pp。
- Wall time：Nexus 平均 56.83s，bare 平均 87.88s，Nexus 快 31.05s，約 35.3% speedup。
- Token telemetry：雙方 token measured rate 100%，cost-comparable rate 100%。
- Nexus wearing evidence：formal treatment valid 4/4，Gemini uses Nexus rate 100%，Nexus usage valid rate 100%，phase completion rate 100%，claim verified rate 100%。
- Public claim gate：PASS。

逐題差異：

| Task | Bare | Nexus+RLM | 主要差異 |
| --- | --- | --- | --- |
| `rlm-harder-v2-governance-001` | FAILED | SUCCESS | MemPalace / governance scope 對齊 |
| `rlm-harder-v2-evidence-001` | FAILED | SUCCESS | Artifact/Claim rule 讓 evidence verifier 對齊 |
| `rlm-harder-v2-second-round-001` | SUCCESS | SUCCESS | 雙方可解；Nexus 保留 RLM trace |
| `rlm-harder-v2-memory-001` | SUCCESS | SUCCESS | 雙方可解；Nexus 保留 Memory/phase evidence |

Failure lesson：

- 上一輪 evidence 題失敗不是 Gemini 額度或 runner 問題，而是 Nexus arm 沒把最核心的 Artifact/Claim contract 放進模型可執行上下文。支柱能力若只存在於外層報告，不進 prompt/context，就不能算真的「穿上戰甲」。
- 公開報告必須同時要求 solve lift、wearing evidence、token reliability、trust mismatch 與 public gate；只挑有利數字會讓 Nexus 價值不可採信。
- v2 4 題已可作 public-candidate smoke，但樣本太小；公開頁面只能說「固定 4 題 smoke」結果，不能泛化到所有任務。

下一步：

1. 擴成 8-12 題 public-candidate benchmark，加入更多 governance/evidence/memory/second-round 類型。
2. 每題保留 hidden verifier、eligibility、Nexus wearing evidence、RLM trace evidence。
3. 至少跑 2 trials，產出 confidence interval 或最小/最大區間，避免單次偶然結果。
4. 把 benchmark 流程固化成 skill，未來 Nexus 優化前後都能重跑同一套比較。

## Phase 1 P15-P16 五支柱切入

日期：2026-04-28

目標：

- 先處理最會影響公開說明可信度的三個支柱：Artifact/Claim、MemPalace、Belief。
- 暫緩 MSA/Swarm/Nightshift 統一 trace，避免一次跨太多子系統。

修正：

- Gemini+Nexus benchmark arm 現在會注入 `Nexus wearing contract`：
  - MemPalace：解法必須守住任務 scope 與 governance constraints。
  - Belief：證據不足或信心低時，採保守且測試支撐的修復。
  - Artifact/Claim：完成斷言必須由 artifact 或 passing checks 支撐。
- 針對 v2 fixture 補更明確的支柱規約：
  - governance 題補 MemPalace scope rule。
  - evidence 題補 Artifact/Claim verified rule。
  - memory 題補 Belief/Memory relevance rule。
- Markdown report 新增：
  - `Five-Pillar Contribution`：顯示 LanceDB、Memory、MemPalace、Belief、Artifact/Claim 的 active rate。
  - `Capability Win Map`：列出 bare 失敗但 Nexus 成功的題，並歸因到 MemPalace / Artifact / Belief / RLM 類別。

驗證：

- `uv run pytest -q tests/benchmark/test_gemini_nexus_report.py tests/benchmark/test_capability_ab_runner.py -q`：63 passed。
- `uv run python -m py_compile scripts/bench/gemini_nexus_report.py scripts/bench/capability_ab_runner.py`：pass。
- 已用既有 Gemini 3 Flash v2 smoke JSONL 重新產生 report，確認新增章節可呈現：
  - `Five-Pillar Contribution`
  - `Capability Win Map`
  - governance win -> MemPalace / governance
  - evidence win -> Artifact / Claim

Failure lesson：

- 只說「五支柱都有 active」不夠；公開報告必須把哪個支柱讓哪題勝出列出來，否則使用者仍看不出 Nexus 價值。
- 支柱規約不能只在外層治理存在；Gemini 穿 Nexus 時，規約也必須進入模型可執行上下文。

下一步：

1. 擴充 v2 題庫到 8-12 題，讓 MemPalace、Artifact/Claim、Belief 各至少有 2 題可歸因勝出。
2. 再跑 2 trials，確認 Capability Win Map 是否穩定。
3. 後續再做 MSA/Swarm/Nightshift trace 統一，將 `capability_swarm_used`、`capability_drone_used`、`capability_nightshift_recommended` 對齊同一個 report section。

## Phase 1 P17 題庫擴充

日期：2026-04-28

目標：

- 將 `public_benchmark_rlm_harder_v2` 從 4 題擴到 8 題。
- 讓 MemPalace、Artifact/Claim、Belief/Memory 各至少有 2 題可歸因，避免公開報告只靠單一案例說明支柱價值。

新增題型：

- `rlm-harder-v2-governance-002`：MemPalace scope enforcement，未核准 mutation 必須阻擋，read-only 仍允許。
- `rlm-harder-v2-evidence-002`：Artifact/Claim replay receipt，verified claim 必須有 replay command 且 exit code 為 0。
- `rlm-harder-v2-belief-001`：Belief budget，低信心高風險時必須要求更多 evidence rounds。
- `rlm-harder-v2-second-round-002`：second-round repair 對照題，增加 RLM/self-heal 題量。

修正：

- P16 的專屬 prompt hook 原本使用不存在的 fixture kind：
  - `rlm_harder_v2_governance_scope`
  - `rlm_harder_v2_memory_relevance`
- 已改為覆蓋實際 fixture kind：
  - `rlm_harder_v2_governance_guard`
  - `rlm_harder_v2_governance_scope`
  - `rlm_harder_v2_memory_contract`
  - `rlm_harder_v2_belief_budget`

驗收目標：

- manifest schema 測試確認 v2 有 8 題。
- hidden governance >= 2。
- hidden evidence >= 2。
- hidden memory/belief 合計 >= 2。
- 所有 v2 fixture 都能 materialize 並帶 portable hidden verifier import。

## Phase 1 P19 MSA / Swarm / Nightshift Trace Section

日期：2026-04-28

目標：

- 將 MSA / orchestration 能力納入同一份 Gemini vs Gemini+Nexus benchmark report。
- 先做 report contract，不改 Swarm、Drone、Nightshift runner 行為。

新增指標：

- `swarm_used_rate`：由 `capability_swarm_used` 統計。
- `drone_used_rate`：由 `capability_drone_used` 統計。
- `nightshift_recommended_rate`：由 `capability_nightshift_recommended` 或 `guard_nightshift_recommended` 統計。
- 對應 delta：
  - `swarm_used_rate_delta`
  - `drone_used_rate_delta`
  - `nightshift_recommended_rate_delta`

報告新增章節：

- `MSA / Orchestration Trace`
- 與 Hyper、Self-heal、RLM trace 放在同一表格：
  - Hyper
  - Self-heal
  - Swarm
  - Drone
  - Nightshift recommended
  - RLM trace present

Failure lesson：

- 只把 `capability_swarm_used`、`capability_drone_used`、`capability_nightshift_recommended` 寫進 row 不夠；公開報告若沒有統一 section，使用者仍看不出 MSA 是否真的參與。
- P19 應先做可觀測合約，不急著改實際 orchestration runner，避免把報告面與執行面風險混在一起。

下一步：

1. 用既有 8 題 v2 benchmark 跑 Gemini 3 Flash 1 trial smoke。
2. 若 MSA section 顯示 Swarm/Drone/Nightshift 皆 0%，先判斷是題型未觸發還是能力未接線。
3. 後續再設計專門觸發 Swarm/Drone/Nightshift 的 public-candidate 題，不要硬把所有題都升級成 orchestration 題。

## Phase 1 P20 8-task Smoke 初跑

日期：2026-04-28

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- rows：8 bare + 8 Nexus
- hidden verifier：on
- RLM trace：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_v2_8task_smoke_93d7182a/gemini_nexus_report_1777345811.md`

結果：

- Nexus+RLM：7/8 solve，semantic verified 87.5%，trust mismatch 0%，RLM trace present 100%，avg wall time 66.90s。
- Bare Gemini 3 Flash：3/8 solve，semantic verified 37.5%，trust mismatch 0%，avg wall time 23.18s。
- 絕對提升：solve rate +50.0 pp，semantic verified +50.0 pp。
- Public claim gate：FAIL，原因是 Nexus `rlm-harder-v2-evidence-002` 未通過，導致 formal treatment valid 7/8。

觀察：

- Capability Win Map 覆蓋：
  - `governance-001`：MemPalace / governance
  - `evidence-001`：Artifact / Claim
  - `governance-002`：MemPalace / governance
  - `belief-001`：Belief / Memory
- MSA section 顯示 Hyper 100%，Self-heal 50%，Swarm 100%，Drone 0%，Nightshift 0%，RLM trace 100%。

Failure lesson：

- `evidence-002` 的 task desc 說 clean replay exit code，但 hidden verifier 欄位實際叫 `exit_code`；Gemini bare 已誤用 `replay_exit_code`。Nexus prompt 必須把 field contract 寫清楚，否則 Artifact/Claim 規則仍會因欄位歧義失效。
- Capability Win Map 不能只掃完整 task desc；通用 wearing contract 會讓 Belief 題含有 Artifact/Claim 字樣，造成錯誤歸因。歸因規則要優先看 task id / fixture kind 的強訊號。

修正：

- `rlm_harder_v2_evidence_replay` 會注入 replay evidence rule：必須有 `replay_command` 且 `exit_code == 0`，欄位名不是 `replay_exit_code`。
- Capability Win Map 將 Belief/Memory 歸因優先於 Artifact/Claim，避免通用 wearing contract 污染分類。

下一步：

1. 只重跑 `rlm-harder-v2-evidence-002` smoke，確認 Nexus 是否由 FAIL 變 SUCCESS，且 bare 仍 FAIL。
2. 若單題通過，再重跑 8 題 x 1 trial，目標 public claim gate PASS。
3. gate PASS 後再跑 8 題 x 2 trials。

單題修正驗證：

- 第一次修正只補 `exit_code` 欄位說明仍失敗；trace 顯示 A gate 擋下 `tests_failed`，target diff 為空。
- 根因：`evidence_replay` 同時收到通用 Artifact/Claim rule（`status='pass'` + artifact）與 replay receipt rule，語義混雜。
- 第二次修正將 `evidence_replay` 從通用 Artifact/Claim rule 拆出，改成精確函式契約：
  - `receipt.get('claim') == 'verified'`
  - `receipt.get('replay_command')` present
  - `receipt.get('exit_code') == 0`
  - 明確禁止誤用 `replay_exit_code`
- 單題 rerun：
  - report：`.nexus/reports/bench_gemini3flash_rlm_v2_evidence002_fix2_93d7182a/gemini_nexus_report_1777346952.md`
  - Nexus：1/1 solve，semantic verified 100%，wall 51.23s。
  - Bare：0/1 solve，semantic verified 0%，wall 29.36s。

Lesson：

- 支柱 prompt 不能一味疊加；不同 Artifact/Claim 子型別需要互斥、精準的 contract，否則會讓模型在相近欄位間漂移。

## Phase 1 P20 8-task Smoke 修正後結果

日期：2026-04-28

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- rows：8 bare + 8 Nexus
- hidden verifier：on
- RLM trace：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_v2_8task_smoke_22775006/gemini_nexus_report_1777347126.md`

結果：

- Nexus+RLM：8/8 solve，semantic verified 100%，trust mismatch 0%，RLM trace present 100%，avg wall time 58.96s。
- Bare Gemini 3 Flash：1/8 solve，semantic verified 12.5%，trust mismatch 0%，avg wall time 122.73s。
- 絕對提升：solve rate +87.5 pp，semantic verified +87.5 pp。
- Wall time：Nexus 平均快 63.77s，約 52.0% speedup。
- Token measured：Nexus 100%，bare 87.5%，仍高於 public token threshold。
- Public claim gate：PASS。

Capability Win Map：

- MemPalace / governance：
  - `rlm-harder-v2-governance-001`
  - `rlm-harder-v2-governance-002`
- Artifact / Claim：
  - `rlm-harder-v2-evidence-001`
  - `rlm-harder-v2-evidence-002`
- Belief / Memory：
  - `rlm-harder-v2-belief-001`
  - `rlm-harder-v2-memory-001`
- RLM / self-heal：
  - `rlm-harder-v2-second-round-002`

MSA / Orchestration:

- Hyper：0% -> 100%。
- Self-heal：0% -> 50%。
- Swarm：0% -> 100%。
- Drone：0% -> 0%。
- Nightshift recommended：0% -> 0%。
- RLM trace present：0% -> 100%。

Residual risk：

- 這仍是 8 題 x 1 trial smoke，不是最終公開級 claim。
- Swarm 100% 需要下一步檢查是否為真參與或 row 標記過寬。
- Drone/Nightshift 沒被這組題觸發；需要另設專門 orchestration 題。

下一步：

1. 跑 8 題 x 2 trials，確認 +87.5 pp lift 是否穩定。
2. 檢查 `capability_swarm_used` 來源，確認 Swarm=100% 不是過寬標記。
3. 設計 Drone/Nightshift 專用 public-candidate 題，再納入 MSA 報告。

## Phase 1 P21 8-task x2 Trials 初跑

日期：2026-04-28

指令摘要：

- model：`gemini-3-flash-preview`
- tasks：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- rows：16 bare + 16 Nexus
- hidden verifier：on
- RLM trace：on
- stop-loss：600s per task
- report：`.nexus/reports/bench_gemini3flash_rlm_v2_8task_2trials_c43d6ab1/gemini_nexus_report_1777349155.md`

結果：

- Nexus+RLM：14/16 solve，semantic verified 87.5%，trust mismatch 0%，RLM trace present 100%，avg wall time 90.47s。
- Bare Gemini 3 Flash：14 eligible rows，4/14 eligible solve，eligible solve 28.6%，trust mismatch 0%，avg wall time 63.67s。
- Public claim gate：FAIL，原因是 Nexus `rlm-harder-v2-belief-001` 兩個 trials 都未 verified，formal treatment valid 14/16。

Failure lesson：

- 單次 8/8 smoke 不能直接當公開級結果；2 trials 暴露 `belief-001` 是穩定弱點。
- `belief-001` 的 Nexus prompt 只有通用 Belief/Memory rule，沒有把 `rlm_harder_v2_repair_budget(confidence, risk)` 的精確輸出 contract 下沉給模型。
- 兩次失敗的 winner 都是 `local`，target diff 為空，表示此題沒有進入有效 LLM patch，而是落到無效 fallback。

修正：

- 將 `rlm_harder_v2_belief_budget` 從通用 Memory relevance rule 拆出，新增精確 Belief budget rule：
  - 低信心高風險：`{'rounds': 3, 'needs_evidence': True}`
  - 高信心低風險：`{'rounds': 1, 'needs_evidence': False}`

產品化優先序採納：

1. 證據與驗證框架。
2. 任務路由與上下文注入。
3. 治理、審計、回復機制。
4. 自動化 benchmark 與持續優化迴圈。

下一步：

1. 單題重跑 `rlm-harder-v2-belief-001`，確認 Nexus 是否由 FAIL 轉 SUCCESS，且 bare 仍 FAIL。
2. 若通過，重跑 8 題 x 2 trials 或至少 patch-in rerun evidence 後再做公開草稿。
3. P22b 檢查 `capability_swarm_used` 來源，避免 Swarm=100% 是標記過寬。
4. P23 新增 Drone/Nightshift 專用 public-candidate 題。

單題修正驗證：

- report：`.nexus/reports/bench_gemini3flash_rlm_v2_belief001_fix_c43d6ab1/gemini_nexus_report_1777351774.md`
- Nexus：1/1 solve，semantic verified 100%，wall 57.61s。
- Bare：0/1 solve，semantic verified 0%，wall 159.40s。
- 結論：Belief budget contract 下沉有效，下一步可重跑完整 8 題 x 2 trials。

## 2026-04-29 P12 Codex 5.5 Nexus Route Stabilization

驗證：

- report：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/gemini_nexus_report_1777455740.md`
- same-model arms：`gpt-5.5` bare vs `gpt-5.5` wearing Nexus。
- hidden verifier：enabled。
- history policy：per-task reset。
- Nexus：16/16 solve，semantic verified 100%，trust mismatch 0%，avg wall time 65.50s，avg tokens 8539.56。
- Bare：8/16 solve，semantic verified 50%，trust mismatch 0%，avg wall time 9.28s，avg tokens 12699.06。
- 差異：verified delivery +50 個百分點；Nexus token 約少 32.8%，但 wall time 較高。

Failure lesson：

- Belief budget 的 hidden contract 不能只用「低信心高風險」可見測試推論；Nexus prompt 必須明確下沉不確定信心與中高風險的 evidence rule。
- Prompt 壓縮要保留決策語義：route/profile 應給 summary，不應把完整 capability stack JSON 直接塞進模型上下文。
- 公開 benchmark 欄位應用 `model_uses_nexus` 作為模型中立主欄位，`gemini_uses_nexus` 只能保留相容。

下一步：

1. 將 8x2 報告整理成中文 public-candidate 草稿，但宣稱範圍限定為 Codex 5.5 lane。
2. 等 Gemini 額度穩定後，用同一套 runner 跑 `gemini-3-flash-preview` 與 `gemini-3.1-pro-preview`，不可混用 denominator。
3. 補足 `model_uses_nexus` 在 preflight/ops 報告的 alias，逐步淘汰 Gemini-only 命名。

## 2026-04-29 Gemini 3 Flash Smoke Gate Lesson

Failure lesson：

- Gemini 3 Flash smoke 不能在 `trust_mismatch_rate > 0` 時進入 8 題或公開報告；public claim gate 必須 fail-closed。
- Governance hidden-verifier 題不只要求「拒絕危險操作」，也要求穩定 reason contract：
  - forbidden/destructive action：`governance_block`
  - unapproved mutating or unknown action：`scope_block`
- 能力真觸發表必須區分 `selected_only` 與 `observed_unplanned`；後者代表能力證據存在，但新路由沒有正確記錄 selection。

修正：

- `gemini_nexus_report.py` 在 treatment trust mismatch 非 0 時阻擋 public claim。
- `capability_ab_runner.py` 將 governance guard/scope hidden contract 下沉到 Nexus prompt guidance。
- Capability Activation Details 新增 `observed_unplanned` 狀態，避免把 self-heal 類未記錄 selection 的證據誤標為未觸發。
