# NEXUS P28 Next-Round Main Axis Execution Board (Fail-Closed)

Date: 2026-05-13
Status: IN_PROGRESS (not closed)
Rule: 不可宣稱 HL/HS 結案；無證據即 FAIL。

## Scope (P28 起下一輪主軸)
1) 修 R/hyper 真瓶頸，不再只修報表。
2) semantic failure sensor 必須實際影響 retry/escalation。
3) model-required 任務必須產生 model-owned delivery。
4) learning closure 必須變成可執行 policy update，不只是紀錄。
5) 重跑 Flash same-model A/B（model-required slice）。

## Baseline Evidence (read-only)
- R/hyper 瓶頸仍在：
  - docs/reports/NEXUS_R_HYPER_RUNNER_OVERHEAD_P22_2026-05-13.md
  - docs/reports/NEXUS_R_HYPER_RUNNER_OVERHEAD_P27_FAILCLOSED_2026-05-13.md
- model-required uplift gate 已誠實化，但不是最終目標：
  - docs/reports/NEXUS_MODEL_REQUIRED_UPLIFT_GATE_2026-05-13.md

## Ticket Board (single-owner, machine-checkable)

### P28-T1 R/HYPER REAL BOTTLENECK CUT
Owner: engine-repair
Lane: Runtime performance
Priority: P0

Task
- 降低 R phase / hyper sprint wall time，保持 fail-closed 與 model_uplift_eligible。

Code Entry
- nexus/app/research_flow_service.py
- nexus/research/sprint_service.py
- scripts/bench/capability_ab_runner.py

Required Deliverables
- .nexus/reports/p28_t1_flash_nexus_6task/evidence_bundle.json
- .nexus/reports/p28_t1_flash_nexus_6task/benchmark_rows.jsonl
- docs/reports/NEXUS_P28_T1_R_HYPER_COST_REPORT.md

Acceptance Checks
- AC1: Flash+Nexus `model_uplift_eligible_rate == 1.0` (model-required suite)
- AC2: Flash+Nexus `trust_mismatch_rate == 0.0`
- AC3: `avg_phase_wall_r_sec` 相比 P22 基準下降 >= 20%
- AC4: `avg_runner_overhead_sec <= 1.0`
- AC5: 若 AC1/AC2 任一不成立，整票 FAIL

Fail Conditions
- 只改善報表欄位而未改善 R/hyper wall
- 以放寬 timeout 掩蓋瓶頸

---

### P28-T2 SEMANTIC SENSOR -> RETRY/ESCALATION ENFORCEMENT
Owner: governance-routing
Lane: Sensor-to-action coupling
Priority: P0

Task
- 讓 semantic failure sensor 從「訊號」變成「行為約束」：禁止 blind retry、觸發 escalation 能落到 capability/state 變更。

Code Entry
- nexus/engine/harness_sensors.py
- nexus/engine/harness_route_policy.py
- nexus/engine/capability_planner.py

Required Deliverables
- .nexus/reports/p28_t2_sensor_enforcement/sensor_action_trace.json
- .nexus/reports/p28_t2_sensor_enforcement/planner_decision_trace.json
- docs/reports/NEXUS_P28_T2_SENSOR_ACTION_REPORT.md

Acceptance Checks
- AC1: 觸發 semantic failure 時，trace 中 `retry_policy.allow_blind_retry == false`
- AC2: 觸發 semantic failure 時，必有 escalation 路徑（capability 狀態改變或 reason 帶 escalation）
- AC3: 新增/更新測試覆蓋上述行為，pytest 全綠
- AC4: 至少 1 個真實 benchmark 任務可觀測到 sensor->action 連動

Fail Conditions
- 僅有 sensor payload，沒有下游行為改變

---

### P28-T3 MODEL-OWNED DELIVERY HARD GUARANTEE
Owner: benchmark-integrity
Lane: Model-required governance
Priority: P0

Task
- model-required 任務最終成功交付必須為 model-owned source；local 只能作為 blocked evidence。

Code Entry
- nexus/research/sprint_service.py
- scripts/bench/benchmark_eligibility.py
- scripts/bench/capability_ab_runner.py

Required Deliverables
- .nexus/reports/p28_t3_model_owned_contract/evidence_bundle.json
- .nexus/reports/p28_t3_model_owned_contract/eligibility_audit.json
- docs/reports/NEXUS_P28_T3_MODEL_OWNED_REPORT.md

Acceptance Checks
- AC1: model-required rows 中 success rows 的 `nexus_winner_source` 全為 model-source
- AC2: local winner 一律被標記 `model_required_local_delivery_blocked`
- AC3: `model_uplift_eligible` 僅在 model-owned delivery 為 true

Fail Conditions
- 仍存在 success + local winner_source 組合

---

### P28-T4 LEARNING CLOSURE -> EXECUTABLE POLICY UPDATE
Owner: learning-loop
Lane: Runtime learning governance
Priority: P0

Task
- 將學習閉環輸出提升為可執行 policy（含 promotion gate），不是只寫 phase_writeback。

Code Entry
- nexus/engine/learning_policy_loader.py
- nexus/engine/capability_planner.py
- nexus/research/learn_mode.py

Required Deliverables
- .nexus/policy/promoted_s2t_policy_draft.json
- .nexus/reports/p28_t4_learning_policy/policy_promotion_audit.json
- docs/reports/NEXUS_P28_T4_LEARNING_POLICY_REPORT.md

Acceptance Checks
- AC1: policy schema/status 合法（nexus_promoted_s2t_policy_draft_v1）
- AC2: runtime_promotable=true 時，planner selection 有可觀測決策變更（非僅 shadow）
- AC3: promotion gate 不過時不得套用 runtime policy（fail-closed）
- AC4: 回歸測試覆蓋 draft/shadow/promoted 三態

Fail Conditions
- 只有 writeback 記錄，沒有 runtime policy 生效證據

---

### P28-T5 FLASH SAME-MODEL A/B RERUN (GATED)
Owner: benchmark-ops
Lane: Evidence closure
Priority: P0

Task
- 針對 model-required slice 重跑 Flash same-model A/B，驗證 T1~T4 之後的真實提升。

Command Baseline
- `uv run python scripts/bench/capability_ab_runner.py --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json ...`

Required Deliverables
- .nexus/reports/p28_t5_flash_same_model_ab/evidence_bundle.json
- .nexus/reports/p28_t5_flash_same_model_ab/ab_eval_summary.json
- docs/reports/NEXUS_P28_T5_FLASH_AB_REPORT.md

Acceptance Checks
- AC1: `model_uplift_eligible_rate == 1.0`
- AC2: `trust_mismatch_rate == 0.0`
- AC3: Flash+Nexus wall ratio 相對同模型 bare 顯著下降（門檻由本輪基準鎖定）
- AC4: 如 hidden verifier 未開，必須標註 gate 未完成，不得宣稱 public claim

Fail Conditions
- 只提供 aggregate，缺少 row-level evidence
- 未明確標註 gate 狀態就宣稱 close

## Week Operating Contract
- Mid-run format: SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT
- Verdict set only: PASS / FAIL / BLOCKED
- Any missing evidence file => FAIL

## Immediate Next Step
- 先做 T1+T2（同一輪），因為兩者直接決定 wall-time 與 retry 行為；
- T3/T4 並行；
- 最後 T5 做總驗證。