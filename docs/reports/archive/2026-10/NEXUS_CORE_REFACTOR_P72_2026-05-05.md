# Nexus Core Refactor P66-P72 Report

## [任務]
完成三項架構報告後續收斂：Execution & Belief、Memory & Context、Governance & Events 從第一輪 contract seam 推進到可被主路徑使用與測試阻擋的狀態。

## [數據]
- P66 Recursive Repair：R-loop 優先使用 `ctx.context_hub.belief_engine`，fallback 才建立本地 `BeliefEngine`；audit result 會寫入 `AuditOutcome`。
- P67 Learning Steward：`LearningSteward.decide()` 直接寫 `learning_action`，`LearningGovernance.evaluate()` 透過 typed `learning_decision` event 發布決策。
- P68 ContextHub DI：`engine/bootstrap.py` 建立並注入同一個 `BeliefEngine`、`MemoryService`、`WisdomVault` 到 `ContextHub`。
- P69 StateView：`StateView` 增加 `route_receipts` / `report_receipts` 與 `receipt_summary()`，為 pre-routing/report receipt 審核鋪路。
- P70 Domain Events：typed emitters 覆蓋 `audit_failed`、`learning_decision`、`evidence_accepted`，測試確認 publish contract 與 JSONL persistence。
- P71 Report：本報告落地於 `docs/reports/NEXUS_CORE_REFACTOR_P72_2026-05-05.md`。
- P72 Flash 小回歸：2-task x 1 A/B 完成；With Nexus `2/2`、Bare Flash `2/2`、所有 public gates PASS。此小回歸只證明重構後模型路徑健康，不宣稱 lift。
- P65 基準證據：Flash 12x2 已完成，With Nexus `24/24`、Bare Flash `14/24`、delta `+41.7pp`，所有 public gates PASS。

## [證據]
- Targeted tests: `uv run pytest -q tests/engine/test_recursive_repair_loop.py tests/engine/test_engine_bootstrap.py tests/core/test_belief_engine.py tests/core/test_event_bus.py tests/health/test_learning_scorer.py tests/test_policy_manager.py tests/health/test_c_phase_episode.py`
- Targeted result: `35 passed, 1 warning`
- Route smoke: `python3 scripts/ops/capability_route_smoke.py` -> `passed=true`
- Research stack smoke: `python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_route_8oracle_smoke/with_nexus_1777974800.jsonl --require-autoreason-invoked` -> `passed=true`
- P72 Flash small regression report: `.nexus/reports/bench_gemini3flash_value2x1_20260505_p72/gemini_nexus_report_1777975180.md`
- P72 key results: solve rate `100.0% -> 100.0%`, public claim gate `PASS`, capability-specific claim gate `PASS`, selected->invoked `100.0%`, research doctor pass `100.0%`, claim probe gate pass `100.0%`.
- P65 full baseline report: `.nexus/reports/bench_gemini3flash_value12x2_20260505_p65/gemini_nexus_report_1777969816.md`
- P65 key results: solve rate `58.3% -> 100.0%`, public claim gate `PASS`, capability-specific claim gate `PASS`, selected->invoked `97.5%`, research doctor pass `100.0%`, claim probe gate pass `100.0%`.

## [殘債]
- Pro full run remains intentionally skipped until Flash regression remains stable.
- Worktree has unrelated S2T/wiki/.nexus dirty files that are not part of this report.
