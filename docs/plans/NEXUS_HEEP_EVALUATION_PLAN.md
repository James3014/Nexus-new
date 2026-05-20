# Nexus Hybrid-Ensemble Evaluation Plan (HEEP)

## 1. 概述
本計劃旨在評估 Nexus 能力在「單數 Skill (Solo)」與「複數 Skill (Ensemble)」模式下的表現差異。透過量化品質增量與成本代碼，為每項能力設定最佳裝配策略。

## 2. 測試模式定義
- **Mode A: Lean Solo**
    - **組態**：僅使用 V32 評測第一名的 Primary Skill。
    - **目標**：極致速度與最低 Token 成本。
- **Mode B: Dual Guard**
    - **組態**：使用 Primary Skill + Top 1 挑戰者作為監核。
    - **目標**：攔截邏輯錯誤，提升修復成功率。
- **Mode C: Neural Swarm**
    - **組態**：使用 Top 3 候選 Skill 進行多重共識投票。
    - **目標**：消除 AI 幻覺，確保治理與安全真值。

## 3. 核心指標 (Metrics)
1. **品質增量 (Quality Lift)**：Ensemble 模式相較於 Solo 模式的成功率提升百分比。
2. **溢價係數 (Premium Factor)**：每提升 1% 品質所增加的 Token 成本比。
3. **共識一致性 (Consensus Score)**：複數 Skill 間輸出結果的吻合程度。

## 4. 實施流程
1. **Gold Cases 提取**：從歷史報告中提取各能力的「黃金測試案例」。
2. **三路併行測試**：利用修改後的 `nexus_benchmark_full.py` 進行 A/B/C 組對抗。
3. **動態策略標定**：將測試結果回灌至 `NEXUS_CAPABILITY_SKILL_MAP.md`。

## 5. 落地契約修訂 (2026-05-20)

HEEP 不直接接舊式 `nexus_benchmark_full.py` 作為第一步；第一階段改接現有 SF SSOT 與 overlay artifact，先產生可機器檢查的 discovery-only contract。

- **輸入 SSOT**：
  - `docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json`
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json`
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json`
- **執行入口**：`uv run python scripts/ops/build_heep_emas_pipeline.py`
- **產物**：
  - `docs/reports/NEXUS_HEEP_EMAS_CONTRACT_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_GOLD_CASE_MANIFEST_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_LOCAL_ABC_ROLLUP_2026-05-20.json`
  - `docs/info/NEXUS_CAPABILITY_SKILL_MAP.md`
- **邊界**：本階段只做 deterministic local dry-run 與 catalog/mode 更新；`runtime_update_allowed=false`、`public_benchmark_allowed=false`。
- **下一階段**：只有當 live ensemble runner 產出 runtime-confirmed selected/injected/used/evidence/gate/outcome receipt，Mode B/C 才能進 runtime apply review。

## 6. MAT-B 可執行比對契約 (2026-05-20)

HEEP 的最終選用標準不是 local role coverage，也不是單純「複數 skill 比單 skill 看起來完整」。每個 capability 都必須先以目前 primary skill 作為 **Mode A baseline**，再將 Mode B / Mode C 作為 challenger arm 進入 Flash+Nexus internal live compare。local replay 只能產出候選與 receipt readiness，不能直接產生 replacement verdict。

### 6.1 Arm 定義

- **Baseline arm**：`mode_a_current_primary`，只掛目前 `(capability, primary_skill)`。
- **Challenger arm**：`heep_multi_skill`，掛 Mode B 或 Mode C assembly。
- **比較範圍**：同一 capability、同一 task set、同一 runner boundary、同一 hidden verifier / receipt contract。
- **產物入口**：`docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json`。

### 6.2 MAT-B KPI 與判定順序

| 順序 | 維度 | KPI | Gate |
| :--- | :--- | :--- | :--- |
| 1 | Reliability | `success_rate` | challenger 必須 >= baseline，且不得出現 delivery RETURN。 |
| 2 | Quality | `pollution_pct` | challenger 必須 <= baseline，且不得超過該 task family 的污染上限。 |
| 3 | Governance | `evidence_seal_count` | challenger 必須 >= baseline，且 runtime receipt 必須包含 selected / injected / used / evidence / gate / outcome。 |
| 4 | Efficiency | `token_delta`, `wall_delta` | 只有 Reliability、Quality、Governance 全 PASS 後才可判讀；不得用成本改善覆蓋前三項失敗。 |
| 5 | Regression | `reopen_rate` | challenger 必須 <= baseline，且 replay/regression simulation 不得重新打開已關閉問題。 |

`reopen_rate` 的優先來源是 runner 原生欄位。若 runner 尚未輸出原生 `reopen_rate`，HEEP report builder 只能在 row 同時具備 delivery、runtime classification、data contract、cost/evidence/delivery rubric、skill mount contract 與 receipt-chain 信號時，使用 deterministic receipt replay proxy 產生 `0.0` 或 `1.0`。缺少這些 replay inputs 時必須維持 `HOLD_MISSING_MAT_B_EVIDENCE`，不得把空值視為通過。

任何 arm 若出現 `infra_invalid_reason`，該 pair 不得被當作有效勝負比較。baseline infra-invalid 只能 `HOLD_MISSING_MAT_B_EVIDENCE`；challenger infra-invalid 也只能 HOLD。只有 challenger 具備乾淨成本/receipt 證據但 delivery RETURN 時，才可判為 `REJECT_MULTI_SKILL`。

### 6.3 Decision State

- `KEEP_SINGLE_PRIMARY`：Mode A 仍是最佳或 challenger 未通過 MAT-B。
- `PENDING_FLASH_NEXUS_LIVE_COMPARE`：local replay 顯示 Mode B/C 有潛力，但 live KPI 尚未收齊。
- `APPROVE_HEEP_MODE_CANDIDATE`：Mode B/C 在 MAT-B 全部 PASS，可進 runtime apply review packet。
- `REJECT_MULTI_SKILL`：Mode B/C 未通過 Reliability、Quality、Governance 或 Regression。
- `HOLD_MISSING_MAT_B_EVIDENCE`：缺少 live receipt、token/wall truth、污染率或 reopen evidence。

### 6.4 禁止宣稱

- 禁止用 local replay、role count、consensus score 或 synergy factor 直接取代 MAT-B live KPI。
- 禁止將 `APPROVE_HEEP_MODE_CANDIDATE` 等同 runtime default；runtime default 仍需獨立 apply gate。
- 禁止將本 contract 的 internal live compare 等同 public benchmark 或 publication-ready claim。

## 7. Runtime Apply Gate (2026-05-20)

MAT-B approval is a prerequisite for runtime apply review, not runtime mount eligibility. The apply gate must re-read:

- `docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json`
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json`
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_SKILL_STATUS_2026-05-20.json`

The gate output is `docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_2026-05-20.json`.

Required runtime apply conditions:

- MAT-B verdict is `APPROVE_HEEP_MODE_CANDIDATE`.
- Every requested skill is runtime-mount eligible, currently `nexus_curated_candidate`.
- Runtime-final receipt chain has selected / injected / used / evidence / gate / outcome all true.
- `public_benchmark_allowed=false`; public benchmark still requires its own gate.

Initial result: `docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_2026-05-20.json` is `RETURN` because approved assemblies still contain `external_reference_candidate` skills.

Reviewed result: `docs/reports/NEXUS_HEEP_RUNTIME_CURATION_STATUS_2026-05-20.json` curates the 10 required repo-local winner skills for runtime-apply-review input only, and `docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_REVIEWED_2026-05-20.json` is `PASS` for 9/9 approved assemblies.

Apply result: `docs/reports/NEXUS_HEEP_RUNTIME_DEFAULT_APPLY_DECISION_2026-05-20.json` and `docs/reports/NEXUS_HEEP_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-20.json` apply the 9 reviewed assemblies to a runtime overlay artifact. The planner now supports `skill_assembly_by_capability`, so a selected capability can request multiple reviewed skills.

Post-apply smoke: `docs/reports/NEXUS_HEEP_RUNTIME_POST_APPLY_SMOKE_2026-05-20.json` verifies 9/9 applied assemblies with selected / injected / used / evidence / gate / outcome receipts.

This still does not unlock public benchmark.

## 8. MAT-B Blocker Resolution Queue (2026-05-20)

After the reviewed runtime overlay and post-apply smoke, the remaining MAT-B unresolved rows are not skill wins or losses. They are split into explicit repair lanes by `docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json`.

- `21/34` MAT-B comparisons are decided.
- `10/34` are `PROVIDER_TOKEN_TRUTH_REPLAY`: the receipt chain is otherwise clean, but model-call rows lack provider-measured token truth. These rows must be replayed with `token_data_contract_status == PASS`; local token estimation or zero-fill cannot approve a replacement.
- `3/34` are `RECEIPT_INVOCATION_REPLAY`: `drone`, `nightshift`, and `swarm_multi_agent` still miss expected runtime capability receipts (`drone`, `nightshift`, `swarm`). These require targeted route/executor smoke before another MAT-B comparison.

The blocker queue keeps `runtime_update_allowed=false` and `public_benchmark_allowed=false`. It is a repair queue only: no HEEP map update, runtime default apply, or public benchmark may consume a blocked row until its lane-specific closure gate passes.

Matrix repair: `docs/reports/NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json` now sets `NEXUS_ENABLE_SWARM_BENCH_EXECUTOR=1` for `drone`, `nightshift`, and `swarm` MAT-B rows, and the HEEP internal task manifest uses runner-native `all_target_tests_pass` so the benchmark row can be verification-only while MAT-B still judges receipt-chain completeness in the report layer. This does not retroactively approve the blocked rows; it only makes the next targeted replay capable of producing the required executor receipts.

Targeted replay check: a 6-row receipt replay was attempted at `.nexus/reports/heep_flash_nexus_mat_b_receipt_replay_2026-05-20`; the first `drone` row still returned because the model-required delivery path produced `gateway_error` / `model_required_model_delivery_failed` and provider token truth remained invalid. Therefore the three receipt-lane rows are not yet settled; they need a provider-clean replay window after the matrix/manifest repair, not a local pass override.

NEXT replay check: a full 26-row blocked replay was attempted at `.nexus/reports/heep_flash_nexus_mat_b_next_replay_2026-05-20` and summarized in `docs/reports/NEXUS_HEEP_MAT_B_NEXT_REPLAY_STATUS_2026-05-20.json`. The first `direct_master_loop` row was semantically `VERIFIED`, but it still returned because `model_calls=1`, `gateway_error_category=gateway_error`, `raw_provider_total_tokens=0`, and `token_data_contract_status=DATA_CONTRACT_VIOLATION`. Therefore all 13 blocked capabilities remain fail-closed until a provider-clean replay window produces measured provider tokens.

Blocked mode resolution: `docs/reports/NEXUS_HEEP_MAT_B_BLOCKED_MODE_RESOLUTION_2026-05-20.json` separates internal non-cost mode selection from provider-cost/public eligibility. The 10 provider-token blockers have clean receipt/trust chains and stronger challenger evidence, so they are recorded as `MULTI_SKILL_NON_COST_WIN`; they still cannot update runtime or public benchmark until same-window provider-token truth is measured. The 3 receipt blockers (`drone`, `nightshift`, `swarm_multi_agent`) remain `UNDECIDED_RECEIPT_CHAIN_MISSING` because expected executor receipts are still absent.

Final skill decision: `docs/reports/NEXUS_HEEP_MAT_B_FINAL_SKILL_DECISIONS_2026-05-20.json` assigns a usable skill set to all 13 blocked capabilities. The 10 provider-token blockers use the multi-skill set for internal non-cost selection. The 3 executor receipt blockers use the current single primary fallback until executor receipts prove the multi-skill challenger. All selected skill assets resolve to repo-local `SKILL.md` files; runtime defaults and public benchmarks remain blocked.

Executor receipt smoke: `docs/reports/NEXUS_HEEP_EXECUTOR_RECEIPT_ROUTE_SMOKE_2026-05-20.json` passed. The `route_oracles` suite includes `drone`, `nightshift`, and `swarm` in both expected and public-safe capability receipts with no failures. The final skill decision artifact now records `executor_route_smoke_status=PASS` for `drone`, `nightshift`, and `swarm_multi_agent`; their remaining gate is skill-specific MAT-B replay plus provider-clean replay before cost/runtime/public eligibility.

Closure packets: `docs/reports/NEXUS_HEEP_MAT_B_EXECUTOR_TRIO_REPLAY_STATUS_2026-05-20.json`, `docs/reports/NEXUS_HEEP_MAT_B_ROLLUP_V2_2026-05-20.json`, `docs/reports/NEXUS_HEEP_MODE_MAP_UPDATE_GATE_V2_2026-05-20.json`, `docs/reports/NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_V2_2026-05-20.json`, `docs/reports/NEXUS_HEEP_PUBLIC_BENCHMARK_READINESS_GATE_2026-05-20.json`, and `docs/reports/NEXUS_HEEP_TASKCARD_STATUS_R1_R6_2026-05-20.json` close the current N1-N8 / R1-R6 task-card set. A fresh 6-row executor-trio MAT-B replay still stopped at the first `drone` row because the row had `skill_mount_contract_status=RETURN`, `token_data_contract_status=DATA_CONTRACT_VIOLATION`, `gateway_error_category=gateway_error`, missing expected `drone` receipt, and no measured provider token truth. The closure state is therefore explicit: 13/13 blocked capabilities have a usable selected skill set for internal HEEP selection, R3 review refresh is done, but R1/R2/R4/R5/R6 remain fail-closed until provider-clean and skill-specific MAT-B evidence exists.

Provider/receipt RCA: `docs/reports/NEXUS_HEEP_PROVIDER_RECEIPT_BLOCKER_RCA_2026-05-20.json` classifies the current blocker as `WAIT_FOR_PROVIDER_CLEAN_REPLAY_WINDOW_THEN_RERUN_SKILL_SPECIFIC_MAT_B`. The matrix already carries the executor flag for the trio rows, but the first model-required MAT-B row failed before runtime-final receipts could become public-safe. Therefore the missing `drone` receipt is downstream of failed model delivery and missing provider-token truth, not proof that the selected `drone` skill is unusable.

Deterministic route smoke was rerun after the RCA and still passed in `docs/reports/NEXUS_HEEP_EXECUTOR_RECEIPT_ROUTE_SMOKE_2026-05-20.json`; `drone`, `nightshift`, and `swarm` are all present in the route-oracle expected/public-safe capability sets. This narrows the unresolved work to a provider-clean MAT-B replay window, not a route-oracle or skill asset repair.

Executor trio next step: `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_NEXT_STEP_PACKET_2026-05-20.json` now separates local receipt readiness from provider-clean live evidence. `drone`, `nightshift`, and `swarm_multi_agent` all have repo-local skill assets, executor route smoke PASS, and planned receipt chains ready, so their skill-specific receipt next step is `READY_FOR_PROVIDER_CLEAN_MAT_B_REPLAY`. This moves the trio out of generic receipt uncertainty; the only remaining admissible blocker is provider-measured token truth in a clean MAT-B replay window.

Provider-clean replay attempt: `.nexus/reports/heep_flash_nexus_mat_b_executor_trio_provider_clean_replay_2026-05-20` was run for the six executor-trio MAT-B rows and stopped after the first `drone` row, summarized in `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_PROVIDER_CLEAN_REPLAY_STATUS_2026-05-20.json` and `docs/reports/NEXUS_HEEP_PROVIDER_CLEAN_REPLAY_RCA_2026-05-20.json`. The failure matched the previous provider blocker: `token_data_contract_status=DATA_CONTRACT_VIOLATION`, `token_data_contract_reason=model_call_without_measured_provider_tokens`, `gateway_error_category=gateway_error`, `provider_token_measured=false`, and missing expected `drone` receipt. The trio remains ready for the next clean replay window, but no runtime/public gate may consume this attempt.

## 9. SFV2 Single/Multi Skill Selection Pipeline (2026-05-20)

`docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json` is now the single machine-checkable closure artifact for the future automatic selection loop. It covers all 34 capabilities across the full milestone path: source tiering, capability shortlist, single-skill tournament state, multi-skill assembly, role-drop ablation matrix, MAT-B decision normalization, catalog update action, and runtime apply review state.

Current SFV2 summary:

- `34/34` capabilities classified and shortlisted.
- `9` capabilities have approved multi-skill assembly candidates.
- `11` retain the single primary because multi-skill regressed or did not beat the primary.
- `1` rejects multi-skill on reliability/delivery.
- `10` are held by provider-token truth.
- `3` are held by receipt-chain truth.
- `97` role-ablation matrix rows are generated for non-solo assemblies.

The new rule is explicit: role count, local synergy, or a multi-skill mount is not enough. A multi-skill assembly can update internal catalog state only after MAT-B correctness gates, and it can move toward runtime only after runtime-confirmed selected / injected / used / evidence / gate / outcome receipts. Public benchmark remains separate and locked.

Role-ablation probe: `docs/reports/NEXUS_SFV2_ROLE_ABLATION_PROBE_2026-05-20.json` now expands the 9 approved multi-skill assemblies into 29 executable full/minus-role arms. This completes the local role-ablation probe and live-replay plan, but it intentionally does not claim role contribution is live-proven. A role is proven only when the full assembly and every minus-role arm run in a clean MAT-B window and dropping the role worsens a correctness, governance, regression, or receipt KPI without being rescued by token/wall gains.

Role-ablation execution matrix: `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EXECUTION_MATRIX_2026-05-20.json` converts those 29 arms into runner-ready rows and `docs/reports/NEXUS_SFV2_ROLE_ABLATION_TASK_MANIFEST_2026-05-20.json` is now frozen with `benchmark_id=nexus-sfv2-role-ablation-v1`. The first preflight correctly returned when the manifest lacked public-runner top fields; the builder now emits `version`, `frozen`, `benchmark_id`, and `description`, and the preflight passes.

Role-ablation live replay: `.nexus/reports/sfv2_role_ablation_live_2026-05-20/live_summary.json` and `docs/reports/NEXUS_SFV2_ROLE_ABLATION_LIVE_ROLLUP_2026-05-20.json` show 29/29 rows PASS across 9 approved multi-skill assemblies. This proves the full and minus-role arms are executable with clean runtime receipt chains in the current window. It does **not** prove every role is required: because all minus-role arms also passed on the neutral fixture, HEEP must treat role requiredness as `RECEIPT_CLEAN_ROLE_REQUIREDNESS_NOT_PROVEN` until edge-case MAT-B tasks show a quality, governance, regression, or receipt loss when a role is removed.

Role-focused edge-case replay: `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_EXECUTION_MATRIX_2026-05-21.json` adds 20 role-focused tasks and 40 full-vs-matching-minus rows. `.nexus/reports/sfv2_role_ablation_edgecase_live_2026-05-21/live_summary.json` and `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_LIVE_ROLLUP_2026-05-21.json` show 40/40 rows PASS after one targeted provider-window retry on `memory/full_assembly`. The run proves executable edge-case coverage and clean receipt replay for all approved multi-skill assemblies. It still does **not** prove role requiredness: `role_requiredness_proven_count=0` and `role_requiredness_not_proven_count=20`, because every matching minus-role row preserved delivery and receipt cleanliness.

HEEP decision after edge-case replay: keep the 9 multi-skill assemblies as internal candidates, but do not claim Scout / Logic / Audit necessity, do not upgrade runtime defaults from role-ablation evidence, and do not unlock public benchmark. The next evidence step must use tasks where the removed role has an externally checkable loss signal, not only a role-focused prompt instruction.

Failure lesson: clean replay must preserve the distinction between provider-token truth and expected-capability receipt invocation. If they are merged into a generic `HOLD_MISSING_MAT_B_EVIDENCE`, later agents can accidentally rerun the wrong path or misread a provider telemetry gap as a weak skill.

Failure lesson: executor route smoke is necessary but not sufficient for MAT-B promotion. It proves the route oracle can express `drone`, `nightshift`, and `swarm`, but a skill-specific MAT-B row must still prove runtime skill mount confirmation, expected capability receipt invocation, and provider-token cleanliness in the same evidence window.

Failure lesson: do not backfill executor skill receipts on a semantically failed model-required row. Estimated token counts and local fallback traces may support diagnosis, but only provider-measured same-window token data can unblock cost/runtime/public eligibility.

Failure lesson: RCA tests must mirror real replay rows, including semantic status and token data contract fields. A fixture that only says `status=FAILED` can accidentally test an unknown failure as clean, which weakens the provider-clean fail-closed boundary.

Failure lesson: role-ablation task manifests must satisfy the same runner manifest contract as other internal Flash+Nexus matrices. Missing `benchmark_id`, `description`, `frozen`, or `version` must fail preflight instead of being papered over by live execution.

Failure lesson: role-focused task metadata must not be added as arbitrary top-level task fields. The benchmark task schema rejects unknown fields, so role metadata belongs in task text, matrix rows, runner env, and rollup artifacts.

Failure lesson: a clean full/minus role-ablation run is necessary but not sufficient for role requiredness. If the minus-role arm still passes with clean receipts, the evidence supports assembly executability, not a claim that the removed role is necessary.

---
*Created by Antigravity - Nexus Singularity V17*
