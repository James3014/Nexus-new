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
