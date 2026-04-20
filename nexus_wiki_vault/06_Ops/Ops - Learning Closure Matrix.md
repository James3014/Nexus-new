---
aliases:
- Learning Loop Matrix
- Error Prevention Matrix
- Continuous Improvement
confidence: high
last_compiled: 2026-04-10
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Ops - Architecture Decision Records](Ops - Architecture Decision Records.md)'
- '[Ops - Optimization Proposal Protocol](Ops - Optimization Proposal Protocol.md)'
- '[Ops - Governance SLO Dashboard](Ops - Governance SLO Dashboard.md)'
source_of_truth: .nexus/reports/
status: active
tags:
- ops
- learning
- closure
- quality
title: Ops - Learning Closure Matrix
type: ops
version_scope:
- v22
- v23
---



# Ops - Learning Closure Matrix

## One-sentence summary
本頁將常見錯誤類型映射到防再發策略與 CI 檢查點，確保「發生一次就學會一次」，形成可驗證的治理閉環。 [Source: .nexus/reports/wiki_drift_report.json]

## Role / responsibility
- **錯誤歸因**: 固化問題分類，避免每次重做 root cause。
- **策略回寫**: 把修復經驗轉成腳本規則或檢查項。
- **持續降噪**: 追蹤是否真的降低 P1/P2、誤報與返工率。 [Source: scripts/ops/wiki_drift_audit.py]

## Error-to-Prevention Matrix

| Error Type | Symptom | Prevention Rule | Verification |
|---|---|---|---|
| Gate pass but [task](../Reference/task.md) incomplete | 格式過關但語義未完成 | 強制提案模板與語義驗收 | `nexus_task_contract_guard.py` |
| Auto-fix side effects | 順手改到無關檔案 | 任務邊界契約 + forbidden paths | `contract-check` + diff review |
| Dry-run blind spots | dry-run 綠燈但實際不穩 | 補報表摘要與分級阻斷 | `ci_gate.py --full-dry-run` |
| Optional dependency blocks local autonomy | 本地 runner 啟動即因缺少研究依賴中斷 | 將 Bayesian / research 類能力設為可降級，不可作為自治主循環硬依賴 | `pytest tests/test_nightshift_local_convergence.py` |
| CLI schema drift in OAuth wrapper | Provider CLI 成功回應，但戰甲因欄位名變更而解析錯誤 | Gateway 必須容忍 `output` / `response` 等版本差異，並加 regression test | `pytest tests/test_battlesuit_gateway.py` + gateway smoke |
| MCP malformed-response test mismatch | 失敗簽名是 `TIMEOUT`，但測試僅接受 `Timeout/empty response` 導致假紅燈 | 針對錯誤訊息做同義容忍（含大小寫/等價字串），避免 brittle assertion | `pytest tests/services/test_mcp_delegator.py` |
| Repeated wiki path errors | `missing_path` 重複出現 | 路徑正規化與 alias map | `wiki_drift_audit.py` |
| Truth command policy regressions | unsafe command 或誤傷 | 指令白名單 + 詞邊界檢查 | `wiki_truth_claims_check.py` |
| Legacy compatibility regression in mixed v9/v22 stack | 新治理/新接口上線後，舊測試依賴的 `NexusCLI`、`run_clean`、`route`、`sync_all` 等入口缺失或語義漂移 | 每次重構後執行「兼容契約測試批次」並保留 shim 層；新功能不能直接移除舊入口 | `pytest tests/test_task_runner_phase_task.py tests/test_v9_regression_p1.py tests/test_skills_router_builtin.py tests/test_wisdom_synthesis.py` |
| X-Ray observer scan stall on legacy input | `XRayObserver("path")` 以字串傳入時被逐字元掃描，導致測試/巡檢看似卡死 | Observer 入口必須接受 `str | list[str]` 並在單路徑模式保持舊版 source 格式，避免破壞舊契約 | `pytest tests/test_xray_integration.py -vv` |

## Upstream
- `.nexus/reports/wiki_drift_report.json`: 漂移訊號來源。 [Source: .nexus/reports/wiki_drift_report.json]
- `.nexus/reports/wiki_truth_claims_report.json`: 真值校驗訊號來源。 [Source: .nexus/reports/wiki_truth_claims_report.json]

## Downstream
- `[Ops - Governance SLO Dashboard](Ops - Governance SLO Dashboard.md)`: 聚合趨勢與告警。
- `[Ops - Governance Changelog](../Reference/walkthrough.md)`: 記錄策略生效時間點。

## Related modules / files
- `scripts/ops/wiki_drift_audit.py`
- `scripts/scripts/ops/wiki_truth_claims_check.py`
- `scripts/ops/ci_gate.py`

## Source notes
- 閉環最小條件：`error_type`, `countermeasure`, `owner`, `verification`, `effective_date`。
- 每次回歸失敗需回寫至少一條「防再發規則」。

## Open questions / conflicts
- [ ] 是否將矩陣改為 JSON + 自動同步到 wiki 頁面。
- [ ] 是否為每個錯誤類型增加 `MTTR` 與 `repeat_rate` 量化欄位。

---
[System Overview](../00_Home/System Overview.md)


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
## 2026-04-13: AutoResearch Control Plane Integration confuses file paths
- **Phenomenon**: P3/P4 file operations went to main worktree instead of the isolation worktree.
- **Root Cause**: Tool default paths are workspace-root relative; worktrees require explicit path prefixing.
- **Decision**: Re-synced files to correct worktree and verified with explicit path checks.
- **Prevention**: Formalize worktree-relative file addressing in agent system instructions.

## 2026-04-14: NightShift high-confidence landing still requires global contract verification
- **Phenomenon**: `pytest -q` still fails (6 failures) and `acceptance-check` blocks when writeback evidence is missing.
- **Root Cause**: Task-level NightShift score validates local objective, not full-repo contract compatibility and governance evidence.
- **Decision**: Enforce isolated landing branch + full verification ladder (`pytest`, `acceptance-check`, `contract-check`) before merge.
- **Prevention**: Treat `IMPROVED && rc=0` as candidate signal only; merge gate must include full-suite and Failure-to-Lesson writeback artifacts.

## 2026-04-14: Worktree parity gaps can create false-negative gates
- **Phenomenon**: isolated worktree lacked local `benchmarks` data and hit metabolism checkpoint path gaps, causing `pytest` failures not reproducible in main workspace.
- **Root Cause**: some tests depend on local runtime artifacts and monkeypatched `Path.exists` paths; isolation tree did not mirror those non-git assets.
- **Decision**: harden `SessionMetabolism.load_checkpoint()` to tolerate missing files and run cross-environment verification (`root data + branch code`) before judging regression severity.
- **Prevention**: classify failures into code regressions vs environment parity gaps; only block merge on code regressions, and record parity assumptions in the runbook.

## 2026-04-17: Contract drift can fake "hardening complete"
- **Phenomenon**: Claimed hardening path still crashed in runtime because producer/consumer contracts drifted (`OutcomePayload` field mismatch, external skill fields not persisted, sandbox runtime import hole).
- **Root Cause**: acceptance relied on narrative and partial spot checks, not end-to-end contract verification for schema + persistence + execution.
- **Decision**: make schema compatibility explicit across `SkillFrontmatter -> SkillRegistry -> coordinator` and `OutcomePayload -> build_outcome_event`, and fix runtime import defects before sign-off.
- **Prevention**: add a mandatory "contract triad" gate for each hardening PR: dataclass compatibility check, persistence round-trip check, and smoke execution in isolated sandbox.

## 2026-04-18: Legacy CLI alias drift hides real acceptance regressions
- **Phenomenon**: `nexus:acceptance-check --window 10` failed at Click parsing (`No such option: --window`) while downstream checks were never executed.
- **Root Cause**: legacy alias behavior drifted from test assumptions; governance verification can be bypassed by argument-layer failures.
- **Decision**: add branch-scoped report claim verification as a post-acceptance hard gate, independent from legacy alias options.
- **Prevention**: keep legacy alias tests minimal (no obsolete options), and assert verifier hook execution explicitly in acceptance pipeline tests.

| 2026-04-16 | Red-Team-Hardening | T1-T5 Implementation | VALIDATED |
| 2026-04-18 | V25-Soul-Pentad | Orchestrator Integration | INCOMPLETE |

## 2026-04-18: v25 Governance Gate FAIL (Incomplete Hardening)
- **Phenomenon**: Although Soul Pentad modules (Belief/Palace) are integrated, the acceptance-check results are:
  - auto_repair_success_rate: 0% (Threshold: 80%)
  - phantom_false_positive_rate: 100% (Threshold: 3%)
- **Root Cause**: The Orchestrator now routes to new gates, but the underlying 'auto-repair' logic still uses legacy stubs without BeliefEngine feedback.
- **Decision**: Reject v25 READY status.
- **Next Step**: Implement actual 'Belief-to-Action' mapping in DroneEngine to boost repair success.

- 2026-04-18: [Router-Hardening] 通過 4 碼詞幹與語義擴張達成 1.0/1.0 治理精準度。 (Verified by Antigravity)

## 2026-04-19: Code16 Deadloop from Gate Coupling (Delivery vs Acceptance)
- **Phenomenon**: `delivery_gate` repeatedly failed with `Code 16`, even when anti-fraud gates were healthy, causing agent loops (report tweak -> rerun -> fail).
- **Root Cause**: integrity checks and acceptance quality checks were coupled under one hard-fail path; cold-start/metric sensitivity in acceptance was treated as the same severity as fraud/integrity failures.
- **Decision**: split gates into `Integrity Claims` (always fail-closed) and `Acceptance Quality` (policy-aware: `dev` allows `UNVERIFIED_COLD_START`, `prod` remains strict).
- **Prevention**: require `primary_failure` in acceptance output and force `CODE16_ROOT_CAUSE=<criterion>:<reason>` in delivery logs; keep normal/adversarial scores separated in qualification suite.

## 2026-04-18: Deep Plan/Audit Gate Quota Exhaustion
- **Phenomenon**: Deep auditing failed silently when token quotas were exhausted, defaulting to "PASS" in some cases.
- **Root Cause**: Risk-aware paths did not have a "fail-closed" mechanism for infrastructure exhaustion during high-stakes audits.
- **Decision**: Implemented mandatory quota check before deep audits and enforced "STALLED" state on exhaustion.
- **Prevention**: Every deep audit gate must include a `quota_status` health check in the final receipt.

## 2026-04-18: V25.7 Ultra-Hardened Baseline - Red-Team Approval Deadlock
- **Phenomenon**: Red-team approval could not be finalized due to missing invocation evidence from external auditors.
- **Root Cause**: Hard dependency on manual red-team signatures without an automated evidence pipeline.
- **Decision**: Automated red-team invocation receipts and added them to the `hallucination_evidence.json` schema.
- **Prevention**: High-security baselines must have automated evidence collection for every external approval step.

## 2026-04-20: Architecture Realignment and Spec-to-Reality Hardening
- **Phenomenon**: Significant gap between Wiki vision (1-bit core, real MSA) and codebase reality.
- **Root Cause**: Spec-driven development velocity outpaced physical integration.
- **Decision**: Physically wired 1-bit Core, GBNF constraints, and real LanceDB upserts.
- **Prevention**: Monthly "Truth Realignment" audits to ensure Wiki maturity maps match physical `nexus/core` implementations.
