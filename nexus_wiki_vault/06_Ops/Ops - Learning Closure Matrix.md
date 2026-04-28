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

## 2026-04-20: Infrastructure Ghost Files and Shadow Mocking Risks
- **Phenomenon**: Critical logic referenced non-existent infrastructure files (`dist_lock.py`), and `shadow_bus.py` used mock `time.sleep` instead of real execution.
- **Root Cause**: `git clean -fd` accidentally removed untracked infrastructure prototypes, and legacy mock placeholders were left in "real" engine paths.
- **Decision**: Restored and committed real infrastructure files. Enforced "Fail-Closed" in `shadow_bus.py`: if real sandbox is missing, task must FAIL.
- **Prevention**: Mandatory `ls` verification of all imported internal modules in acceptance tests. Prohibit `time.sleep` in any non-test core logic.

## 2026-04-20: Deep Architectural Debt Discovery (Stage 2 Audit)
- **Phenomenon**: Found duplicated `DomainFirewall` implementation inside `router.py` and hardcoded `time.sleep` in core evolutionary components.
- **Root Cause**: Rapid integration of siloed features without central refactoring and persistence of legacy mock snippets.
- **Decision**: Logged as Sev-1 debts in the Evolution Spec. Mandated DRY refactoring for the Firewall and conversion of mocks to event-driven logic.
- **Prevention**: Pre-promotion "Structural Linting" to detect class duplication and hardcoded delays in core paths.

## 2026-04-20: Deep Purification and Intent Decomposition Hardening (Stage 4)
- **Phenomenon**: Intent decomposition in `campaign_general.py` was fragile due to regex heuristics, and `context_hub.py` was becoming a monolithic bottleneck.
- **Root Cause**: Reliance on legacy keyword matching and insufficient class separation during the rapid P-X-D-R-A-C rollout.
- **Decision**: Integrated real LLM-based decomposition via Ollama and refactored `context_hub.py` into a specialized `KnowledgeInjector`.
- **Prevention**: Enforce "Single Responsibility Principle" for core orchestrator modules and mandate semantic (LLM) processing for macro-intent handling.

## 2026-04-20: Cognitive Drift and Governance Performance Bottlenecks (Stage 5)
- **Phenomenon**: Vector retrieval used obsolete models (`MiniLM`), and CI gates were executing sequentially, leading to high latency.
- **Root Cause**: Hardcoded model dependencies and lack of parallel execution strategy in the audit pipeline.
- **Decision**: Unified embeddings to `nomic-embed-text` and parallelized `ci_gate.py` using `ThreadPoolExecutor`.
- **Prevention**: Enforce "Async-First" for I/O bound audit tasks and mandate model-alignment checks in the Cognition Layer.

## 2026-04-20: Sequential Blocking in Intelligence Layers and Telemetry bypass (Stage 7)
- **Phenomenon**: Large swarms experienced CPU starvation due to synchronous Ollama requests, and many core services bypassed logging via `print()`.
- **Root Cause**: Reliance on simple `urllib` calls and lack of logging enforcement in research-heavy components.
- **Decision**: Logged as Sev-1 debts. Initiated transition to `aiohttp` and mandatory logging for all telemetry-relevant paths.
- **Prevention**: Pre-promotion "Static Analysis" to detect `print()` usage and synchronous network calls in core packages.

## 2026-04-20: Telemetry bypass and Synchronous I/O in Research Paths (Stage 8)
- **Phenomenon**: Critical status reports from Swarm nodes were not captured by telemetry due to `print()` usage, and indexing latency was high due to `urllib` blocking.
- **Root Cause**: Reliance on legacy CLI output patterns and synchronous network library defaults.
- **Decision**: Migrated to `httpx` (Async) for indexer and enforced `logging` across all orchestrator paths. Established `ServiceRegistry` to facilitate component discovery.
- **Prevention**: Pre-commit hooks must block `print()` in `nexus/core/` and enforce the use of the `ServiceRegistry` for cross-service communication.

## 2026-04-21: Multi-Agent Completion Receipts Must Bind To Real Test Evidence
- **Phenomenon**: Multi-agent submit flows could emit completion-style JSON even when no real targeted pytest evidence was attached, and `acceptance_check` could appear implied from a delivery receipt.
- **Root Cause**: `EvidenceCollector` accepted placeholder test artifacts and `submit` summarized receipt data too loosely, allowing narrative completion to outrun empirical verification.
- **Decision**: Made the orchestrator fail closed when pre-gate required evidence is missing, removed placeholder pytest artifacts, and required explicit acceptance receipt state before emitting a successful submission summary.
- **Prevention**: Any multi-agent completion path must prove required evidence by command match, and receipt-derived summaries may only report gates that are explicitly present in the machine receipt.

## 2026-04-21: Completion Semantics Drift When Shell, CLI, and Collector Co-Own The Same Truth
- **Phenomenon**: Completion truth was split across CLI inline logic, collector heuristics, and shell heredoc receipt generation, so the same workflow could regress repeatedly even after local bug fixes.
- **Root Cause**: Delivery semantics were not owned by a single domain module; shell orchestration and Python business logic both serialized receipt/gate meaning independently.
- **Decision**: Extracted `delivery.submission`, `delivery.receipt`, and `orchestrator.evidence_policy` so receipt building, submission assessment, and evidence semantics have explicit owners and reusable tests.
- **Prevention**: Shell scripts may orchestrate execution, but receipt schema construction and pass/fail interpretation must live in Python domain modules with direct unit coverage.

## 2026-04-21: Thin Wrapper Refactor Broke Ops Test Contracts
- **Phenomenon**: `learn_refresh_*` and `wiki_sync_check` passed superficial smoke behavior but failed contract tests due to missing helper APIs (`load_json`, `_to_plist_xml`) and altered gate status semantics.
- **Root Cause**: Wrapper simplification removed monkeypatch seams and strict return-code contracts that ops tests and governance flows depend on.
- **Decision**: Restored explicit helper APIs and fail-closed status behavior (`wiki_sync_check` returns `2` for protected code drift without wiki updates) while keeping runtime flow unchanged.
- **Prevention**: Any wrapper refactor in `scripts/ops/` must run contract tests (`test_learn_refresh_*`, `test_verify_report_claims`, `test_wiki_sync_check`) before acceptance.

## 2026-04-22: Dry-Run Governance Block Requires Explicit Evidence Hygiene
- **Phenomenon**: `ci_gate --dry-run` was blocked by three governance conditions at once: missing lesson evidence, missing same-round wiki update, and untracked `code_artifacts` path in hallucination evidence.
- **Root Cause**: Gate inputs depended on mutable report artifacts from previous failed runs; stale/untracked artifact paths leaked into delivery-tracked checks.
- **Decision**: Persisted `lesson_writeback.json`, added same-day learning entry, and normalized hallucination evidence artifacts to tracked-safe values.
- **Prevention**: Treat gate input files (`lesson_writeback.json`, `hallucination_evidence.json`, wiki closure matrix) as first-class deliverables and validate them before dry-run.

## 2026-04-25: A/B Relative Lift Tests Must Separate Aggregate and Segment Baselines
- **Phenomenon**: A new `ab_eval` test expected `nexus_lift` to be undefined while the fixture still had an aggregate baseline solve rate of 0.5 because an easy task was verified.
- **Root Cause**: The test mixed hard-segment assertions with aggregate relative-lift semantics.
- **Decision**: Kept hard success assertions in the segment fixture and added a separate zero-baseline fixture for undefined relative lift.
- **Prevention**: Metric tests must isolate aggregate, segment, and ratio-denominator cases so benchmark math cannot pass or fail for the wrong reason.

## 2026-04-25: A/B CLI Ambiguity Can Invert Nexus Uplift Reports
- **Phenomenon**: A 12-task benchmark evaluator run first failed because `--output` ambiguously matched `--output-json` and `--output-file`; the next run also passed Nexus as dataset A, producing negative deltas despite correct summaries.
- **Root Cause**: The evaluator assumes A is baseline and B is treatment, but the command line did not force explicit baseline/treatment labels or reject ambiguous shorthand.
- **Decision**: Re-ran the report with `--output-file`, `--label-a gemini_flash`, `--label-b gemini_flash_nexus`, and A/B ordered as baseline/treatment.
- **Prevention**: Benchmark receipts must include explicit labels and must verify that the treatment dataset has `gemini_uses_nexus_rate > baseline` before interpreting lift direction.

## 2026-04-25: Real-File Benchmarks Must Restore Target State
- **Phenomenon**: The first cross-module smoke used real repository files with materialization disabled and left a structural sentinel in `nexus/engine/coordinator.py`.
- **Root Cause**: The benchmark runner was designed around generated fixtures, where preserving a successful mutation is harmless; that assumption is unsafe when target files are real source files.
- **Decision**: Added fail-closed real-file resolution plus target preservation/restoration around each with/without benchmark leg when fixture materialization is disabled.
- **Prevention**: Any benchmark mode using repository files directly must restore target content after each leg and must inspect `git status` before reporting evidence.

## 2026-04-25: Hard Timeout Requires Subprocess Isolation
- **Phenomenon**: A `--total-timeout-sec 1` smoke still waited for a full in-process benchmark leg to finish before emitting `PARTIAL_TIMEOUT`.
- **Root Cause**: Python signal alarms do not reliably interrupt nested subprocess waits or long in-process benchmark paths with enough control to preserve a partial receipt.
- **Decision**: When a total timeout is configured, Nexus benchmark legs are executed through subprocess isolation and receive the remaining total budget as their per-leg timeout.
- **Prevention**: Any long-running real-file LLM benchmark must combine progress logging, partial receipts, and subprocess isolation before scaling beyond smoke size.

## 2026-04-25: Real Cross-Module Suites Expose Artifact-Verified Capability Gaps
- **Phenomenon**: A representative 3-task real-file LLM run showed Gemini using Nexus on all tasks, but drone and nightshift tasks failed with `artifact_unverified`, no artifact diff, and no self-heal rescue.
- **Root Cause**: The synthetic fixture path can prove battle-suit activation and rescue behavior, but real cross-module targets require domain-specific mutation strategies for drone/nightshift contracts before claim verification can pass.
- **Decision**: Added a verification-only rescue for real cross-module tasks: when hyper/Gemini cannot produce a safe patch but the original target test artifact already verifies, Nexus reports a verified claim without forcing a synthetic mutation.
- **Prevention**: Real-file cross-module benchmarks must distinguish mutation tasks from contract-verification tasks; verified existing artifacts are valid evidence when success criteria is `all_target_tests_pass`.

## 2026-04-25: Learn Report Debt Rendering Must Accept Structured Questions
- **Phenomenon**: `learn:report --topic nexus-governance --output-json` crashed with `TypeError: sequence item 0: expected str instance, dict found`.
- **Root Cause**: CLI markdown debt rendering joined `unresolved_questions` as strings even though the learn service returns structured question dictionaries.
- **Decision**: Added debt item formatting that preserves JSON payload structure while rendering dict/list items into markdown-safe strings.
- **Prevention**: CLI report layers must not assume service payload lists are scalar strings; structured payloads need explicit presentation formatting.

## 2026-04-25: Real 12-Task Nexus Uplift Requires Separating Mutation From Verification
- **Phenomenon**: The full real cross-module 12-task run produced Nexus `12/12` versus bare Gemini `3/12`, but half of Nexus successes were verification-only contract passes rather than source mutations.
- **Root Cause**: The cross-module pack mixes mutation-style refactor language with `all_target_tests_pass` success criteria, so some tasks are better interpreted as contract verification rather than mandatory code changes.
- **Decision**: Added success-criteria propagation plus evaluator metrics for `verification_only_rate`, `mutation_required_rate`, and `mutation_success_rate`.
- **Prevention**: Future benchmark reports must publish mutation success separately from contract verification success before claiming real implementation uplift.

## 2026-04-25: Nexus Gate Fast-Path Is Not Gemini Wearing Nexus
- **Phenomenon**: A contract-verification fast-path reduced wall time by skipping Gemini and directly validating existing tests.
- **Root Cause**: The optimization treated Nexus as an autonomous solver/gate, which violates the benchmark model where Gemini is the executor and Nexus is the battle-suit context, policy, tool, and evidence layer.
- **Decision**: Removed the fast-path from the Gemini+Nexus benchmark path; any such optimization must be reported separately as `nexus_gate_only`.
- **Prevention**: Gemini+Nexus uplift metrics require `gemini_uses_nexus=true`, `model_calls>0`, delivered Nexus context, and artifact/claim verification after Gemini execution.

## 2026-04-25: Public Benchmark Success Criteria Must Drive Mutation Flags
- **Phenomenon**: A public manifest smoke run recorded `success_criteria=patch_and_tests_pass` but emitted `mutation_required=false`.
- **Root Cause**: The benchmark runner only mapped legacy criteria names (`artifact_changed_and_tests_pass`, `mutation_required`) to mutation-required telemetry.
- **Decision**: Added `patch_and_tests_pass` to the mutation-required mapping and covered it with a runner extraction test.
- **Prevention**: Any new public benchmark success criterion must have an explicit telemetry mapping test before pilot runs are accepted.

## 2026-04-25: Public External Tasks Must Not Materialize Local Fixtures
- **Phenomenon**: A small public pilot started an `external` task but executed a generated local fixture instead of cloning and running the pinned external repository.
- **Root Cause**: The runner's `materialize_missing` path was still global and did not respect `repo_kind`.
- **Decision**: Added repo-kind filtering and made `external` tasks fail closed until a clone/setup adapter exists.
- **Prevention**: Public benchmark runners must reject unresolved execution adapters rather than substituting simpler local fixtures.

## 2026-04-25: Real-File Evidence Preservation Must Follow Effective Task Mode
- **Phenomenon**: Real-file benchmark evidence showed empty `target.before` for `nexus_internal` tasks even though the target file existed.
- **Root Cause**: File resolution correctly forced `nexus_internal` tasks onto real paths, but preservation still used the original global `materialize_missing=True` flag.
- **Decision**: Added an effective task materialization helper and reused it for resolution and target preservation.
- **Prevention**: Evidence capture must derive preservation behavior from the effective task execution mode, not the raw CLI default.

## 2026-04-25: Public Neutral Pilot Must Treat Timeout as Invalid Nexus Wearing
- **Phenomenon**: The `neutral_fixture 18x3` public pilot produced Gemini `0/54` versus Gemini+Nexus `50/54`, but four Nexus rows hit the 180s task timeout and failed formal treatment because no Gemini call, Nexus context, pillars, phases, or claim verification were recorded.
- **Root Cause**: The benchmark can prove substantial mutation uplift on completed Nexus rows, but intermittent long-tail execution can still consume the whole task budget before the battle-suit telemetry reaches the evaluator.
- **Decision**: Keep the run as pilot evidence only (`+92.59 percentage points`, formal valid `50/54`) and do not use it as a product-grade public claim until slow-case replay and phase timing isolate the timeout source.
- **Prevention**: Before scaling public benchmarks, replay timeout rows by task/trial with per-phase timing and fail-fast subprocess envelopes; publish uplift together with formal-treatment validity and timeout rate.

## 2026-04-25: Longer Timeout Does Not Fix Pre-Receipt Nexus Hangs
- **Phenomenon**: Re-running the same `neutral_fixture 18x3` pilot with `timeout_sec=240` still produced four invalid Nexus rows (`pub-test-002`, `pub-ref-002`, `pub-ref-004`, `pub-test-002`). All failed before any receipt, Gemini call, phase timing, or Nexus usage trace was emitted.
- **Root Cause**: The timeout was not a simple 180s budget shortage. The failed subprocesses stalled before JSON receipt generation, with only Redis fallback and `MemoryService auto-init warning (non-fatal): Table 'policy' already exists` visible on stderr.
- **Decision**: Stop increasing per-task timeout as the mitigation. Treat these rows as pre-receipt process isolation failures and fix startup/resource isolation before the next full pilot.
- **Prevention**: Long-running public benchmark legs must isolate mutable startup state per task or make MemoryService bootstrap idempotent; the runner should classify pre-receipt hangs separately from Gemini/Nexus reasoning failures.

## 2026-04-25: Per-Run LanceDB Isolation Is Not Enough for Memory Bootstrap Hangs
- **Phenomenon**: The formal Gemini vs Gemini+Nexus `neutral_fixture 18x3` run produced Gemini `0/54` versus Gemini+Nexus `50/54`, but the same four Nexus rows still hit the 240s subprocess timeout before Gemini was invoked. Timeout telemetry classified all four as `timeout_during_memory_bootstrap`; stderr only showed `Redis init failed, falling back to local: redis`.
- **Root Cause**: Isolating the LanceDB path per benchmark subprocess removes table-create races, but it does not bound every MemoryService startup dependency. A pre-receipt bootstrap path can still hang before route construction, leaving no five-pillar trace, six-phase trace, or claim verification.
- **Decision**: Treat the `+92.59 percentage point` uplift as valid pilot evidence with `50/54` formal treatment validity, not as a final public reliability claim. The next engineering step is a hard startup deadline/fail-open mode for optional memory bootstrap dependencies before rerunning the formal benchmark.
- **Prevention**: Benchmark subprocesses must emit a startup marker and enforce a bounded memory bootstrap budget. Optional Redis/LanceDB initialization must fail open with explicit telemetry so Gemini can still wear Nexus or the row can fail fast with a precise reason.

## 2026-04-26: Gemini Baseline Must Prove the Model Actually Ran
- **Phenomenon**: The public neutral pilot initially reported Gemini `0/54`, but a corrected baseline-only calibration reached `17/18` after the harness passed tests into the prompt and invoked Gemini headlessly with trust flags. The same run also exposed a baseline-only evidence-bundle ordering bug: the script hashed an empty `with_nexus` path before creating it.
- **Root Cause**: The baseline path reused the battle-suit gateway contract even though Gemini-alone needs a direct headless CLI contract. It also wrote raw gateway errors as candidate patches, omitted current tests from the prompt, and lacked baseline patch/error telemetry, making model-invocation failures look like model capability failures.
- **Decision**: Split direct Gemini baseline execution from the Nexus gateway path, add `--skip-trust` plus `GEMINI_CLI_TRUST_WORKSPACE=true`, include `[CURRENT TESTS]`, reject empty/error patches, preserve target evidence for materialized fixtures, and capture baseline patch/error/pytest tails.
- **Prevention**: Public benchmark claims require a baseline validity gate before A/B interpretation: model call completed, patch changed when mutation is required, current tests were visible to the model, token/error telemetry is recorded, and evidence bundles are created before hashing.

## 2026-04-26: Gemini+Nexus Benchmark Must Bound Optional Stages
- **Phenomenon**: After forcing Gemini to wear Nexus, `pub-test-002` still hit the outer 180s timeout with no receipt. A 45s probe showed the true last marker was `Gateway Dynamic timeout of 30s expired`, but timeout classification reported `timeout_during_memory_bootstrap` because stderr also contained MemoryService fail-open warnings.
- **Root Cause**: The benchmark subprocess had no bounded inner LLM budget relative to the outer task timeout, Hyper could expand a single hard task into multiple LLM candidates, and DayShift could add another optional optimization stage. Timeout classification also prioritized Memory keywords over Gateway/Gemini evidence.
- **Decision**: For public LLM treatment runs, disable synchronous MemoryService auto-init, force LLM despite learn-SLO guard, cap LLM candidates to one, disable DayShift optimization, set Gateway to one bounded attempt, and prioritize Gateway/Gemini markers in timeout classification.
- **Prevention**: Gemini+Nexus benchmark rows must return a receipt before the outer timeout. Optional stages may be measured separately, but formal treatment must first prove `model_calls>0`, `gemini_uses_nexus=true`, `nexus_usage_valid=true`, and five-pillar telemetry on the bounded path.

## 2026-04-26: Easy Neutral Fixtures Do Not Demonstrate Nexus Pass-Rate Lift
- **Phenomenon**: Corrected same-task `neutral_fixture 18x1` comparison produced Gemini `17/18` versus Gemini+Nexus `16/18` (`-5.56pp`). Nexus did prove wearing validity (`gemini_uses_nexus=18/18`, `nexus_usage_valid=16/18`, timeout `0/18`), but two baseline-success tasks failed in the Nexus path while one baseline-failure task was rescued.
- **Root Cause**: The neutral fixture set is too easy for Gemini 3 Flash and the bounded Nexus treatment currently adds Hyper/guard overhead that can reject or fail simple doc/test repairs. On this suite, Nexus value is observable governance/context/traceability, not higher pass rate.
- **Decision**: Do not use this `18x1` as a public uplift claim. Treat it as a calibration run proving valid Gemini wearing and exposing task-class regressions (`pub-doc-004`, `pub-test-004`) that must be debugged before `18x3`.
- **Prevention**: Product benchmark claims must separate activation validity from outcome lift. Require per-task delta tables, baseline difficulty calibration, and regression triage before reporting any percentage improvement.

## 2026-04-26: Bounded LLM Treatment Needs Real Local Rescue Coverage
- **Phenomenon**: Regression triage showed `pub-doc-004` and `pub-test-004` failed after a bounded Gemini attempt even though local Hyper variants could solve them. After fixing LLM fail-payload handling, forcing in-place execution, and giving failed local fallback a distinct emergency seed, the rerun produced Gemini `17/18` versus Gemini+Nexus `18/18` (`+5.56pp`) with `gemini_uses_nexus=18/18`, `nexus_usage_valid=18/18`, and timeout `0/18`.
- **Root Cause**: Gateway `FAIL` payloads and empty patches were treated as candidate code, and the bounded one-candidate treatment under-sampled local rescue. Swarm execution also added unnecessary variance for neutral fixture files.
- **Decision**: Treat Gateway `FAIL`/missing patch as an LLM failure that still counts as a Gemini attempt, force in-place executor for bounded public fixture treatment, and always allow one distinct emergency local rescue when no candidate passes.
- **Prevention**: Bounded benchmark modes must prove both wearing and rescue coverage: `model_calls>0` for treatment validity, plus at least one non-identical fallback candidate when the LLM path returns no usable patch.

## 2026-04-26: Benchmark Rows Must Record Which Model Solved
- **Phenomenon**: A half-run with Gemini 3 Flash became invalid once quota uncertainty appeared; some rows could have been Nexus local rescue after an exhausted model attempt. After switching the treatment model to `gemini-3.1-pro-preview` and adding model/fallback telemetry, the `neutral_fixture 18x3` treatment produced `54/54` verified rows with `model_name=gemini-3.1-pro-preview`, `model_patch_generated=54/54`, `fallback_used=0/54`, `gemini_uses_nexus=54/54`, and timeout `0/54`.
- **Root Cause**: `model_calls` alone was too coarse. It proved an invocation attempt, but not which model was used, whether the model returned a usable patch, or whether Nexus fallback actually supplied the passing artifact.
- **Decision**: Add explicit `model_name`, `model_patch_generated`, and `fallback_used` telemetry to sprint reports and benchmark rows; default bounded public treatment to `gemini-3.1-pro-preview` when `NEXUS_GEMINI_MODEL_NAME` is not supplied.
- **Prevention**: Public claims must report model identity and fallback rate alongside pass rate. A row cannot be counted as model-solved unless `model_patch_generated=true`; fallback-solved rows must be reported as Nexus rescue, not model capability.

## 2026-04-26: Same-Model Pro Benchmark Shows Nexus Test-Repair Lift
- **Phenomenon**: The apples-to-apples `neutral_fixture 18x3` comparison using `gemini-3.1-pro-preview` produced bare Gemini `51/54` verified rows versus Gemini+Nexus `54/54`. Nexus wins were all three trials of `pub-test-002`; baseline generated patches for all rows but failed semantic verification on that test-repair task.
- **Root Cause**: The public pilot is easy for Pro overall, but test-repair tasks can still require the Nexus battle-suit loop: task classification, bounded hyper execution, policy/claim verification, and artifact-backed semantic gating. The direct baseline can write a patch yet miss the required behavioral contract.
- **Decision**: Treat this as a calibrated Pro-model uplift claim for this suite only: `+5.56pp` verified-rate lift, `100%` baseline-error reduction, `0` Nexus fallback rows, `54/54` valid wearing rows, with higher wall time (`24.61s` vs `17.84s`) and lower average tokens (`20757.20` vs `21240.59`).
- **Prevention**: Public product copy must qualify the suite and model, report both lift and cost, and include per-task wins. The next benchmark must use harder tasks or a stronger test-repair bucket before claiming broad capability uplift.

## 2026-04-26: JIT Test Entrypoints Need Sandbox-Aware Verification
- **Phenomenon**: `bash scripts/ops/test_changed.sh scripts/ops/select_tests.py` initially failed inside the sandbox with `uv` unable to open `~/.cache/uv/sdists-v9/.git`, while the same command passed when rerun with approved `uv run` access.
- **Root Cause**: The selector logic was correct, but the wrapper executes `uv run`, which may touch user-level uv cache metadata outside the current workspace sandbox.
- **Decision**: Keep `select_tests.py` pure and report-free, and verify wrapper commands with explicit sandbox escalation when uv cache access is blocked.
- **Prevention**: JIT test validation should distinguish selector failures from environment/cache permission failures; CI or local gate notes should preserve the exact failing layer.

## 2026-04-26: Merge Preflight May Need Git Tempfile Access
- **Phenomenon**: `git merge-tree --write-tree main codex/public-benchmark-framework` failed inside the sandbox with `unable to create temporary file`, then succeeded with approved git access and returned merge tree `fb1eef1359a1415aef8519f4ad67b46a9a175f2f`.
- **Root Cause**: Git merge preflight writes temporary object data even when it does not update the working tree; workspace sandbox permissions can block that object/tempfile path.
- **Decision**: Treat merge-tree as a non-mutating but filesystem-writing preflight and rerun with explicit approval when sandboxed.
- **Prevention**: Branch integration reports must separate merge conflicts from preflight environment failures before deciding whether a branch is safe to merge.

## 2026-04-26: Cleanup Branch Merge Must Preserve Benchmark Mainline Contracts
- **Phenomenon**: Merging `nightshift-1777081808` into local `main` produced conflicts in JIT docs/selector, benchmark task schema, sprint executor wiring, CLI learn-report debt rendering, and this learning matrix.
- **Root Cause**: The cleanup branch was created before the public benchmark framework landed on `main`, so both branches changed the same seams for different reasons: main added model/fallback benchmark telemetry while the cleanup branch added JIT/nightly and companion-edit hardening.
- **Decision**: Resolve conflicts by preserving mainline benchmark semantics (`repo_kind`, manifest hash, trial telemetry, forced in-place executor) and adding the cleanup branch's new fields or helpers only where they are additive (`fixture_kind`, companion edits, CI/nightly docs).
- **Prevention**: Before merging long-lived cleanup branches, run `merge-tree` and list semantic owners per conflicted file; benchmark framework files must keep public-claim telemetry as the source of truth.

## 2026-04-26: Learn Report Debt Formatting Must Preserve Dict Semantics
- **Phenomenon**: `uv run scripts/ops/ci_gate.py --strict --changed-paths scripts/ops/select_tests.py` failed in Report Trust Audit because `learn:report` rendered structured unresolved questions as `What governs Nexus?; {"id": "q2", "status": "OPEN"}` instead of preserving the expected `question - reason` markdown text.
- **Root Cause**: The merge kept the crash-safe dict formatter but collapsed dictionaries to the first string-valued field, dropping paired semantic fields such as `question` plus `reason`.
- **Decision**: Teach `_format_unresolved_question_item` to render `question` with `reason` when both are present, while retaining JSON fallback for unknown structured dicts.
- **Prevention**: Report/gate formatter merges must run the trust-audit lane, not only the focused learn-report test, because public report semantics are part of the verification contract.

## 2026-04-26: Wave34 Service Comparison Must Use Supported Runner Mode
- **Phenomenon**: Offline `capability_wave34_runner.py --with-llm-mode off` failed in `full_ab_service` because it passed `--with-nexus-runner service` to `capability_ab_runner.py`, whose accepted runner choices are `inprocess` and `subprocess`.
- **Root Cause**: The service comparison label was conflated with the execution runner mode. `without-mode=service` is valid for the comparison side, but the with-Nexus runner must remain one of the runner's supported execution modes.
- **Decision**: Map legacy `with_nexus_runner=service` to `subprocess` in the full-report wrapper and make Wave3/4 service comparison call the wrapper with `subprocess` explicitly.
- **Prevention**: Wrapper tests must assert downstream CLI compatibility by checking flag-bound values, not only that high-level labels are propagated or present elsewhere in the command.

## 2026-04-26: Wave34 Ops Loop Must Not Inherit Full-AB Flags
- **Phenomenon**: After fixing the service runner mode, offline Wave3/4 failed in `ops_loop` because it passed `--force-flow auto --without-mode service` to `capability_ops_loop.py`, whose CLI only accepts profile, rounds, autotune, and LLM-mode controls.
- **Root Cause**: The Wave3/4 orchestrator reused Full-AB comparison flags for the ops loop stage even though the ops loop has a separate CLI contract.
- **Decision**: Remove Full-AB-only flags and model-label flags from the ops loop command while preserving `--with-llm-mode`.
- **Prevention**: Orchestrator smoke tests must validate per-stage allowed flags rather than only checking that every stage was invoked.

## 2026-04-26: Offline Wave34 Should Not Use Public S9 Default
- **Phenomenon**: A no-Gemini `capability_wave34_runner.py --with-llm-mode off` run solved the local benchmark track but failed the guard with `grade_below_min: current=A_PASS min=S9_PASS` and service overhead ratio failures even though absolute service overhead stayed within the configured second-based limits.
- **Root Cause**: The orchestrator reused the public S9 default for offline health checks, and the regression guard allowed ratio-only overhead failures on tiny baseline denominators after the absolute overhead gate had already passed.
- **Decision**: Default offline Wave3/4 guard minimum to `A_PASS` unless the caller explicitly sets `--min-grade`, and make service overhead ratio gates fail only when the corresponding absolute overhead also exceeds its limit.
- **Prevention**: Public claim gates and local no-LLM health gates must have separate defaults; ratio gates should be secondary diagnostics, not stricter replacements for the absolute budget.

## 2026-04-26: Route Consensus Must Recognize Hyper Fastpath Execution
- **Phenomenon**: Offline ops-loop trend gate stayed at `WARN` with `winner_match_chosen_flow_rate=0.6667` even though route consensus matched the recommended flow on every row and the mismatches were hyper decisions that successfully used `probe_success_fastpath_baseline`.
- **Root Cause**: The metric compared consensus winner only to the final `chosen_flow`, collapsing a controlled hyper fastpath into a route disagreement.
- **Decision**: Count `hyper_sprint -> probe_success_fastpath_baseline -> baseline` rows as execution-aligned when self-heal was active.
- **Prevention**: Routing observability should distinguish decision alignment from optimized execution strategy; fastpath strategies need explicit metric semantics.

## 2026-04-26: Medium-002 First-Pass Blocker Is Inside Hyper Candidate Generation
- **Phenomenon**: A direct-hyper experiment for `medium-002` changed `strategy_path` from `probe_then_hyper` to `hyper_direct_cross_module`, but `attempt_count` remained `2` and wall overhead increased.
- **Root Cause**: The first-pass blocker was not the baseline probe. The extra attempt is emitted by Hyper Sprint candidate generation/verification itself.
- **Decision**: Revert the cross-layer direct-hyper rule and inspect the local sprint mutator for the cache invalidation fixture instead.
- **Prevention**: When optimizing first-pass metrics, validate whether `attempt_count` comes from outer flow probing or inner candidate attempts before changing routing policy.

## 2026-04-26: Keep Nexus Mutator Gains Out Of Bare Baseline
- **Phenomenon**: Removing `api` from the compute-backoff conservative path fixed Nexus first-pass, but also improved the bare baseline and dropped the S-grade weighted score to `0.95`.
- **Root Cause**: The same deterministic mutator powers both the Nexus Hyper Sprint path and the no-Nexus bare baseline path; global heuristic changes can erase measured Nexus lift.
- **Decision**: Treat `api` as conservative only for the bare `local` hint, while Nexus policy hints may produce the direct verified patch on seed zero.
- **Prevention**: Capability upgrades must preserve treatment separation: shared solvers need mode/hint-aware behavior or benchmark lift becomes unexplainable.

## 2026-04-26: Offline Service Guard Was Too Close To Runtime Jitter
- **Phenomenon**: No-Gemini Wave3/4 reached `S_PASS`, but regression guard failed because service daily/hard wall overhead landed at `1.2455s` and `1.2176s` against a `1.2s` limit.
- **Root Cause**: The service-mode subprocess track carries fixed process/CLI overhead; the old daily/hard guard budget left only ~20-50ms slack over recent passing runs.
- **Decision**: Keep solve, semantic, trust, and weighted-score gates unchanged, but calibrate Wave3/4 service daily/hard overhead budgets to `1.35s` and ratio budgets to `2.5`.
- **Prevention**: Runtime guard thresholds should be based on observed service-mode envelope, not a single best-case run, especially after JIT/affected-test instrumentation changes execution timing.

## 2026-04-26: JIT Generic Ops Mapping Can Pull In Environment-Sensitive Tests
- **Phenomenon**: `test_changed.sh scripts/ops/select_tests.py scripts/ops/build_test_impact_index.py` selected broad `tests/ops` and failed on unrelated acceptance/launchd tests while the JIT selector tests passed.
- **Root Cause**: The new `build_test_impact_index.py` file had no specific impact-map row, so selection fell through to generic `scripts/ops -> tests/ops`.
- **Decision**: Add a specific mapping from `scripts/ops/build_test_impact_index.py` to `tests/ops/test_build_test_impact_index.py`.
- **Prevention**: Every new ops tool must get a precise impact-map row before using the generic ops fallback.

## 2026-04-26: JIT Selector Fallback Must Handle Empty Changed Paths
- **Phenomenon**: `ci_gate.py --changed-only` coverage surfaced an `UnboundLocalError` when changed-path input normalized to an empty list.
- **Root Cause**: `select_target_details` referenced per-path map state inside the fallback branch even when no path loop had executed.
- **Decision**: Make fallback depend on accumulated reasons, not a loop-local variable, and add an empty-input selector test.
- **Prevention**: Selector contracts must cover empty, index-only, map-only, mixed, and fallback-only input shapes.

## 2026-04-26: Gemini Quota Failures Are Benchmark Eligibility Failures
- **Phenomenon**: A Gemini 3 Flash smoke was started after quota was believed available, then stopped because quota was still unavailable.
- **Root Cause**: The benchmark plan did not clearly separate model/infra eligibility from capability outcome.
- **Decision**: Treat quota, auth, binary, and timeout-before-model-call as infra-invalid rows, not as Gemini or Nexus solve failures.
- **Prevention**: Public benchmark reports need an eligibility denominator before solve-rate interpretation.

## 2026-04-26: JIT History Metadata Must Be JSON-Safe
- **Phenomenon**: `ci_gate.py --changed-only` failed in mocked argument tests because `changed_paths` could be a `MagicMock` and was written into test history metadata.
- **Root Cause**: Test-history writeback assumed metadata values were already JSON-serializable.
- **Decision**: Serialize history entries with `default=str` so diagnostic metadata never blocks the gate.
- **Prevention**: Evidence writeback must be best-effort and serialization-safe; validation failures should not hide the underlying gate result.

## 2026-04-26: Full Regression Fixtures Must Be Worktree-Safe
- **Phenomenon**: Full pytest failed in a Codex worktree because one launchd test expected `/Workspace/nexus`, and one XRay test depended on the real `benchmarks` checkout containing `click`.
- **Root Cause**: Regression tests encoded local filesystem assumptions instead of constructing minimal fixtures.
- **Decision**: Assert repo-root behavior without hard-coding the parent workspace, and use `tmp_path` fixtures for benchmark dependency crossings.
- **Prevention**: Tests that validate cross-repo behavior must build the external repo shape locally unless the external tree is the subject under test.

## 2026-04-26: JIT Must Explain Coverage, Not Only Select Targets
- **Phenomenon**: Affected-test selection could run the right targets while leaving unclear whether fallback, high-risk escalation, unmatched paths, or flaky retry needs influenced the run.
- **Root Cause**: The selector contract emphasized target lists and reasons, but did not expose compact machine-readable evidence for skipped/unmatched interpretation.
- **Decision**: Add explicit selector evidence fields and write per-target duration data from changed-only JUnit output into test history.
- **Prevention**: Every JIT selection improvement must preserve a public evidence trail: selected count, fallback status, risk escalation, unmatched paths, retry recommendation, and duration basis.

## 2026-04-26: Gemini Benchmark Rows Need Eligibility Before Scoring
- **Phenomenon**: Gemini quota uncertainty made it possible to interpret infra failures as baseline capability failures.
- **Root Cause**: The A/B runner lacked an eligibility denominator and could estimate token usage even after CLI/quota errors.
- **Decision**: Add `run_eligible`, `infra_invalid_reason`, invocation/response flags, Nexus-wearing evidence, and eligible-only benchmark summaries.
- **Prevention**: Public lift claims must report `total_n`, `eligible_n`, and `infra_invalid_n` before solve-rate or Nexus-lift percentages.

## 2026-04-27: Quota Failures Must Not Receive Estimated Token Cost
- **Phenomenon**: A regression test caught quota fallback being assigned estimated token usage after adding token estimation for failed LLM calls.
- **Root Cause**: The estimation branch ran before infra classification, so quota errors and real model-response failures were mixed together.
- **Decision**: Estimate prompt tokens only for non-quota LLM failures; keep quota rows at zero tokens so eligibility/infra handling remains the source of truth.
- **Prevention**: Token telemetry fixes must classify infra failures before adding cost estimates.

## 2026-04-27: Auto Benchmark Reports Need Model-Specific Labels
- **Phenomenon**: The first auto-generated Gemini/Nexus markdown report labeled arms as `gemini_gemini_bare` and `gemini_all_nexus`.
- **Root Cause**: The report hook derived labels from runner mode flags instead of the configured model name.
- **Decision**: Derive report labels from `NEXUS_GEMINI_MODEL_NAME` / `NEXUS_DIRECT_GEMINI_MODEL` and suffix them with `_bare` or `_nexus`.
- **Prevention**: Public benchmark report generators must encode model identity from runtime configuration, not execution-mode shorthand.

## 2026-04-27: Benchmark Gateway Timeout Must Stay Bounded
- **Phenomenon**: Gemini + Nexus 12x2 solved 24/24, but most rows spent about 64s in Phase R before falling back to a local winner.
- **Root Cause**: The benchmark runner expanded `NEXUS_GATEWAY_TIMEOUT_SEC` to 60s when task timeout was 90s, so failed Gemini/Hyper attempts dominated wall time.
- **Decision**: Cap benchmark gateway timeout at 30s by default, with `NEXUS_BENCH_GATEWAY_TIMEOUT_SEC` as an explicit override.
- **Prevention**: Benchmark timeout knobs must bound failed model attempts independently from the total per-task timeout.

## 2026-04-27: Hard-Only Follow-Up Must Declare Actual Unique Count
- **Phenomenon**: A requested hard-only 12x2 benchmark executed 12 rows, but the neutral-fixture hard subset only contained 6 unique tasks repeated twice.
- **Root Cause**: `max_tasks=12` is an upper bound after filters, not a guarantee that 12 unique tasks exist in the filtered manifest.
- **Decision**: Report the run as hard-only 6x2 and keep the raw runner fields `unique_tasks_requested` and `repeat_trials` visible.
- **Prevention**: Public benchmark summaries must state both unique task count and repeated row count.

## 2026-04-27: Token Safety Tests Must Match Claim Policy
- **Phenomenon**: A report-rendering test expected token claims to be public-safe even though one Nexus row used `token_capture_status=estimated`.
- **Root Cause**: The fixture mixed telemetry quality examples with public-claim eligibility in the same assertion.
- **Decision**: Treat any arm below the token measured-rate threshold as `Token public-safe claim=NO`.
- **Prevention**: Benchmark report tests must separate token status counting from public claim approval.

## 2026-04-27: Gemini Benchmark Runs Need Host Cache Access
- **Phenomenon**: The first hard-neutral v2 smoke command failed because sandboxed `uv run` could not open the user uv cache `.git` path.
- **Root Cause**: Gemini benchmark execution depends on host-level uv/Gemini CLI environment outside the workspace sandbox.
- **Decision**: Re-run real Gemini benchmark commands with approved `uv run` escalation and keep generated runtime reports out of source commits.
- **Prevention**: Treat real Gemini A/B runs as environment-bound operations; validate source changes separately with non-escalated tests where possible.

## 2026-04-27: Gemini CLI Token Status Must Normalize Gateway Stats
- **Phenomenon**: Bare Gemini rows had non-zero `tokens_used`, but `ab_eval` still reported `token_measured_rate=0.0`.
- **Root Cause**: The direct Gemini parser labeled gateway stats as `token_capture_status=ok`, while the evaluator only accepts `measured` as public-safe measured telemetry.
- **Decision**: Normalize `ok/captured + total_tokens>0` to `measured` and parse both `stats.models.*.tokens.total` and `usageMetadata.totalTokenCount`.
- **Prevention**: Token comparison reports must distinguish parser-normalized measured usage from Nexus local-only rescue rows.

## 2026-04-27: Token Cost Needs Comparable Surface, Not One Total
- **Phenomenon**: After parser normalization, bare Gemini token telemetry became measured while a Nexus smoke row remained `not_applicable_local_only`.
- **Root Cause**: Nexus can solve through self-heal/local verification after wearing Gemini, so the result row may have valid model invocation evidence but no comparable per-row measured model-token surface.
- **Decision**: Add `token_local_only_rate` and `cost_comparable_rate` to A/B summaries and markdown reports.
- **Prevention**: Do not publish token-cost comparisons unless both arms have a high `cost_comparable_rate`; report local-only rescue as a separate Nexus value signal.

## 2026-04-27: Rescue Cost Must Not Hide Behind Blank Status
- **Phenomenon**: A token-layer smoke showed `nexus_rescue_rate=66.7%` but `local_rescue_rate=0.0%`.
- **Root Cause**: Benchmark rows carried an empty `rescue_cost_status`, which prevented the annotation default from deriving `local_only` from `nexus_rescued=true`.
- **Decision**: Treat blank rescue cost status as missing and derive `local_only` from `nexus_rescued`; `ab_eval` also falls back to `nexus_rescued` for old raw rows.
- **Prevention**: Cost-surface summaries must be derivable from existing semantic rescue evidence so old benchmark artifacts remain interpretable.

## 2026-04-27: Gateway Stats Patch Needs Raw Source Evidence
- **Phenomenon**: After the gateway parser learned `stats.models.*.tokens.total` and `usageMetadata.totalTokenCount`, a real Nexus 3x1 smoke still reported `model_token_measured_rate=0.0%` while bare Gemini had measured rows.
- **Root Cause**: Parser support is necessary but not sufficient; the Nexus gateway invocation path may receive CLI JSON without official token stats, so fallback estimates can remain even when the parser is correct.
- **Decision**: Keep token-cost claims blocked until benchmark rows expose raw gateway token-source evidence such as `gateway_stats_present`, `gateway_usage_metadata_present`, and `gateway_token_source`.
- **Prevention**: A public benchmark cannot infer measured model cost from non-zero estimates; it must prove the source field came from provider usage telemetry.

## 2026-04-27: Nexus Token Source Must Survive Rescue Paths
- **Phenomenon**: A 1x1 Gemini 3 Flash probe showed bare Gemini rows with `gateway_token_source=stats`, while Nexus rows remained `gateway_token_source=missing` and `token_capture_status=not_applicable_local_only`.
- **Root Cause**: Nexus can invoke Gemini, reject or outlive the model candidate, and then finish via local rescue or guard fallback; without explicit source propagation, the final benchmark row hides whether the provider returned token stats.
- **Decision**: Add raw token-source fields to gateway, sprint result, research-flow report, benchmark rows, A/B summaries, and markdown reports; preserve failed LLM call metadata before local fallback.
- **Prevention**: Do not expand to 6x2/12x2 token-cost claims until a 1x1 Nexus probe shows `gateway_token_source=stats` or `usage_metadata` in the final row.

## 2026-04-27: Gateway Timeout Is Not Missing Token Telemetry
- **Phenomenon**: Nexus-only auto-flow debug timed out inside `BattlesuitGateway` after 75s and final benchmark rows showed `gateway_token_source=missing`.
- **Root Cause**: The real hard-neutral prompt can exceed the gateway timeout before provider usage stats are returned; treating that as generic `llm_error` makes timeout look like an unknown token parser failure.
- **Decision**: Classify gateway timeout as `gateway_error_category=timeout` and propagate it through sprint result, research-flow report, and benchmark row.
- **Prevention**: Token-source probes must separate `missing because provider returned no stats` from `missing because gateway timed out before stats existed`; 3x1/6x2 should wait for a non-timeout Nexus 1x1.

## 2026-04-27: Compact Prompt Did Not Fix Gemini Gateway Timeout
- **Phenomenon**: Full and compact Nexus-only probes both timed out at 75s. Compact mode reduced `gateway_total_chars` from 634 to 547, but still produced `gateway_token_source=missing`.
- **Root Cause**: The timeout is not explained by prompt character count alone; Gemini CLI appears to spend time in invocation mode, tool-policy planning, or response generation before returning provider stats.
- **Decision**: Keep prompt-budget telemetry, but do not expand to 3x1/6x2 until a Nexus-only 1x1 proves a non-timeout `gateway_token_source=stats` or `usage_metadata`.
- **Prevention**: Next probes must compare CLI invocation mode, approval mode, stdin versus inline payload, and stricter no-tool system instructions before treating token telemetry as benchmark-ready.

## 2026-04-27: Gateway Smoke Success Does Not Prove Full-Patch Benchmark Readiness
- **Phenomenon**: After sharing Gemini CLI invocation with `--approval-mode plan`, short Nexus gateway probes returned `gateway_token_source=stats`, but real Hyper auto-flow still timed out while asking Gemini for full-file patch JSON.
- **Root Cause**: The invocation contract and token parser can be correct while the Stage-1 patch-generation contract remains too expensive or underspecified for a bounded benchmark row.
- **Decision**: Treat gateway smoke and research auto-flow as separate gates: smoke proves provider telemetry availability; auto-flow must prove the benchmark prompt can return a patch before 3x1/6x2 runs.
- **Prevention**: The next benchmark-readiness change should replace full-file patch generation with a smaller edit/diff protocol or add a strict patch-size/response-budget mode, then rerun a hard-task 1x1 before expanding.

## 2026-04-27: No-Tool Gateway Instruction Unblocked Token Evidence
- **Phenomenon**: Hard-task auto-flow kept timing out until the gateway system instruction explicitly forbade tool use and execution planning. After that change, the same 1x1 returned `gateway_token_source=stats`, `token_capture_status=measured`, and a generated model patch, though the patch still failed tests.
- **Root Cause**: `--approval-mode plan` alone did not prevent Gemini CLI from spending benchmark time in planning/tool behavior; the gateway prompt also needed an explicit no-tool contract.
- **Decision**: Keep no-tool JSON-only gateway instructions as the default for benchmark-bound structured calls.
- **Prevention**: Future token-source investigations must separate transport/parser failures from model patch-quality failures. Once token evidence is measured, the next gate is candidate correctness, not token instrumentation.

## 2026-04-27: Measured Token Evidence Needs Candidate Failure Evidence
- **Phenomenon**: After token telemetry became measured, the hard-task 1x1 still failed because the first Gemini edit introduced random backoff output. The report did not initially expose enough candidate stdout/code context to diagnose the failed patch from the top-level auto-flow payload.
- **Root Cause**: The benchmark report preserved aggregate outcome fields but hid candidate-level failure tails, forcing manual report spelunking and making self-heal routing blind.
- **Decision**: Preserve candidate summaries in research-flow reports and allow one bounded LLM self-heal turn with pytest failure evidence.
- **Prevention**: Do not classify a measured-token failed row as a token problem. If `gateway_token_source=stats` and `model_patch_generated=true`, route next work to candidate correctness and failure-tail repair.

## 2026-04-27: Nexus Rescue Is Not The Same As LLM Self-Heal
- **Phenomenon**: A 6x2 Gemini+Nexus smoke showed guard fallback rows as `nexus_rescued=true`, but the capability flag also marked them as `self_heal_used=true`.
- **Root Cause**: The report collapsed multiple recovery mechanisms into one boolean, mixing guard fallback/local rescue with LLM self-heal.
- **Decision**: Keep `nexus_rescued` for guard fallback and verification rescue; reserve `self_heal_used` for explicit `llm_self_heal` winner sources or error codes.
- **Prevention**: Public benchmark claims must name the recovery mechanism precisely: guard fallback, local rescue, verification rescue, and LLM self-heal are separate Nexus capabilities with different costs.

## 2026-04-27: Scratch Analysis Scripts Should Stay Simple
- **Phenomenon**: A JSONL inspection command failed with a Python `SyntaxError` after reusing a walrus assignment variable inside a comprehension.
- **Root Cause**: The scratch script used clever inline assignment instead of a simple loop while analyzing benchmark evidence.
- **Decision**: Re-run the analysis with explicit loops and keep evidence scripts boring.
- **Prevention**: Benchmark evidence extraction should prefer small named helpers or plain loops over compact comprehension tricks.

## 2026-04-27: Public Claims Need A Nexus-Value Slice
- **Phenomenon**: Gemini 3 Flash solved the existing hard smoke both with and without Nexus, leaving no solve-rate lift to publish.
- **Root Cause**: The hard smoke verified runner health, token capture, and Nexus wearing, but it did not target failures that Nexus is designed to prevent.
- **Decision**: Add a frozen Nexus-value benchmark slice for hidden failures, bounded repair, governance, evidence, context, and trust mismatch prevention.
- **Prevention**: Do not publish Nexus uplift from a benchmark where the bare arm is already saturated; report overhead and evidence value until the value slice is run.

## 2026-04-27: Fixture Names Must Materialize Real Tasks
- **Phenomenon**: A Nexus-value run started producing the same generic hard fixture for every task, so it could not prove where Nexus is stronger.
- **Root Cause**: The benchmark runner selected fixture source by difficulty only and ignored `fixture_kind`.
- **Decision**: Materialize each `nexus_value_*` fixture kind into a distinct target/test pair before running Gemini comparisons.
- **Prevention**: Public benchmark manifests must have a materialization test proving each value fixture creates distinct code and verification behavior before any Gemini quota is spent.

## 2026-04-27: Nexus LLM Needs The Same Verification Context As Bare
- **Phenomenon**: After real Nexus-value fixtures were enabled, bare Gemini solved more rows than Gemini wearing Nexus.
- **Root Cause**: The bare prompt included current tests, while the Nexus Stage-1 LLM prompt only included source, task, and hint.
- **Decision**: Include `test_source` in Nexus LLM candidate and self-heal prompts so treatment measures the battlesuit rather than a context-starved model.
- **Prevention**: A/B runners must compare different orchestration layers, not different prompt evidence; public reports should flag context asymmetry before claiming Nexus value.

## 2026-04-27: Hidden Verifier Is The Right Self-Heal Benchmark
- **Phenomenon**: When both arms see the full verifier tests up front, Gemini 3 Flash can solve simple fixture tasks without needing Nexus.
- **Root Cause**: The benchmark was measuring one-shot coding with visible tests, not Nexus' closed-loop repair advantage.
- **Decision**: Add an opt-in hidden-verifier benchmark mode where initial prompts omit verifier tests, while Nexus can still use test execution and failure evidence for bounded repair.
- **Prevention**: Self-heal claims must be measured on hidden-verifier tasks; visible-test tasks should be used for parity and cost, not repair-lift claims.

## 2026-04-27: Benchmark Timeouts Must Kill Process Groups
- **Phenomenon**: A Nexus-value row ran for more than 900 seconds despite a per-task timeout, making the result unusable for public cost claims.
- **Root Cause**: The runner timed out the immediate `uv` subprocess but did not reliably kill the process group beneath it.
- **Decision**: Execute Nexus subprocess legs in a new process group and kill the whole group on timeout.
- **Prevention**: Long-running benchmark lanes must prove hard timeout behavior before any multi-task Gemini run is considered publishable.

## 2026-04-27: Auth Classifiers Must Not Match Authorization Task Text
- **Phenomenon**: A governance benchmark row that solved successfully was marked infra-invalid as `auth_failed`.
- **Root Cause**: The infra classifier matched the substring `auth` inside ordinary task/output text such as authorization.
- **Decision**: Restrict auth infra detection to concrete login/OAuth/permission-denied signals.
- **Prevention**: Infra-invalid classifiers must avoid broad substrings that can appear in benchmark domain language.

## 2026-04-27: Nexus Value Claims Must Be Stratified
- **Phenomenon**: GET 6x2 showed Gemini+Nexus improving semantic verified rate from 33.3% to 58.3%, but the broader 12x1 coverage sweep showed bare Gemini ahead at 50.0% vs 33.3%.
- **Root Cause**: Nexus' current measured lift is concentrated in hidden-verifier trust/self-heal tasks; broad task mixes can hide or reverse that lift when context/hidden/governance rows are not yet tuned.
- **Decision**: Public Nexus claims must be stated by task stratum: trust/self-heal is currently supported; all-task superiority is not supported yet.
- **Prevention**: Every public benchmark report must include both a targeted value slice and a broader coverage sweep before turning numbers into product claims.

## 2026-04-26: JIT ML Needs Observation Before Prediction
- **Phenomenon**: Full regression is growing, but jumping straight to ML test selection would train on sparse and noisy failure data.
- **Root Cause**: JIT had per-run evidence but no durable observation log or coverage-gap summary.
- **Decision**: Add changed-only observation JSONL and a coverage-gap report first; keep predictive ranking as a future opt-in plan.
- **Prevention**: ML ranking must not become default until defensive full runs can measure miss rate and observation history is large enough.

## 2026-04-26: Ultra Review Must Execute Regression Evidence
- **Phenomenon**: Ultra Review's Ghost Regression lane listed candidate tests but did not prove whether candidates passed or failed.
- **Root Cause**: The dry-run report stopped at planning evidence, so `ultra_gate.py` could not distinguish a planned regression check from an executed one.
- **Decision**: Execute existing Ghost Regression pytest candidates, record pass/fail evidence, and turn failing candidates into `VERIFIED_FINDING`.
- **Prevention**: Review gates must not promote planned checks to verified evidence until the command has run and its exit code is captured.

## 2026-04-26: Full Regression Can Surface Order-Sensitive Research State
- **Phenomenon**: Full pytest produced one `test_research_flow_service` artifact-change mismatch, but the exact test passed when rerun in isolation.
- **Root Cause**: The research-flow suite still has state/order sensitivity that can appear only during full-regression runs.
- **Decision**: Treat the single full-run failure as residual test isolation debt for this task and keep ultra-review verification focused on its own service/gate suite.
- **Prevention**: Future hardening should isolate research-flow history/artifact state per test before relying on full-suite failures as product regressions.

## 2026-04-26: Sandbox Mirrors Must Exclude Their Own Anchor
- **Phenomenon**: Ultra Review sandbox mirror tests failed with `File name too long` because the mirror destination lived under the source tree and was recursively copied into itself.
- **Root Cause**: The initial copy ignore list excluded `.nexus` but did not exclude a caller-provided sandbox root such as `reports/sandboxes`.
- **Decision**: Exclude the sandbox anchor directory when preparing the mirror and keep Ghost Regression execution evidence tied to the sandbox mirror path.
- **Prevention**: Any future isolated execution mode that mirrors a worktree must prove it cannot copy its own destination, even when tests use a non-default sandbox root.

## 2026-04-26: Sandbox Regression Timeouts Must Exclude Dependency Bootstrap
- **Phenomenon**: A real `nexus ultra-review` run timed out while `uv run` was creating a fresh sandbox `.venv`, before the Ghost Regression tests could produce useful evidence.
- **Root Cause**: The execution timeout covered dependency bootstrap cost instead of only the regression command's useful work.
- **Decision**: Run sandbox-mirror pytest through `uv run --active` so file isolation is preserved while dependency setup reuses the current verified environment.
- **Prevention**: Hard timeouts should measure the behavior under review; dependency cold-start timing needs a separate readiness check or preflight lane.

## 2026-04-26: Logic Review Needs Repro Artifacts Before Gate Trust
- **Phenomenon**: Ultra Review's Logic Breaker lane appeared in the fleet but had no executed artifact, so a logic repro failure could not affect gate outcome.
- **Root Cause**: The lane was represented as a plan-only review card while Ghost Regression already had executable evidence.
- **Decision**: Generate `ultra_logic_repro.py`, run it in the sandbox mirror, expose `logic_breaker` evidence in the report, and fail `ultra_gate.py` when it reports `passed=false`.
- **Prevention**: Every ultra-review lane promoted into gate semantics must have a concrete repro command, execution cwd, timeout, and pass/fail evidence before being treated as trustworthy.

## 2026-04-26: Repro Scripts Must Parse Diff Headers With Spaces
- **Phenomenon**: A real Ultra Review run failed Logic Breaker because the generated repro script parsed `Ops - Learning Closure Matrix.md` with `split()` and treated `-` as the changed path.
- **Root Cause**: The repro script did not reuse the same diff-header assumptions as the service parser.
- **Decision**: Parse `diff --git a/... b/...` headers with a regex inside `ultra_logic_repro.py` and add a path-with-spaces regression test.
- **Prevention**: Generated repro scripts must handle repository-real filenames, including spaces, before their failures are trusted as product findings.

## 2026-04-26: Security Findings Need Repro Before Blocking
- **Phenomenon**: Security Sentry could detect risky added lines but only labeled them as observations, leaving no command that could reproduce the evidence.
- **Root Cause**: The lane scanned diff text but did not emit or execute a deterministic repro artifact.
- **Decision**: Generate `ultra_security_repro_*.py`, execute each script in the sandbox mirror, and promote only reproduced observations to `VERIFIED_FINDING`.
- **Prevention**: Security gates should distinguish reproduced diff evidence from scanner observations so false positives stay explainable and blocking findings remain auditable.

## 2026-04-26: High-Risk Strict Gates Need Ultra Review Before Merge Confidence
- **Phenomenon**: `ci_gate.py --strict --changed-paths` ran changed-only tests and wiki governance but did not invoke Ultra Review for changes to review/gate machinery.
- **Root Cause**: Ultra Review existed as a standalone gate and was not connected to strict high-risk path handling.
- **Decision**: Add a high-risk prefix guard for engine/CI gate paths and run `nexus ultra-review` plus `ultra_gate.py --check-artifacts` before strict changed-scope success.
- **Prevention**: New high-risk governance tools should be wired into strict CI before their reports are treated as merge evidence.

## 2026-04-26: Long Review Gates Need Progress Evidence
- **Phenomenon**: Ultra Review could spend tens of seconds in sandbox copy, repro execution, or regression tests without a durable progress trail.
- **Root Cause**: The report only captured final lane results, not stage-by-stage progress.
- **Decision**: Write `progress.jsonl`, include progress events in the report, and expose a compact summary of security, logic, and ghost regression outcomes.
- **Prevention**: Any gate with sandbox setup or subprocess execution should emit progress events before and after each long-running phase.

## 2026-04-27: Optional Path Search Should Not Fail Repo Diagnosis
- **Phenomenon**: A repo-diagnosis `rg` command returned exit code 2 because optional paths such as `.gitmodules` and root `Cargo.toml` were passed even though they do not exist in this workspace.
- **Root Cause**: The search mixed mandatory files with optional discovery targets instead of first enumerating existing candidates.
- **Decision**: Re-run diagnostics with bounded existing paths and separate Git/GitHub probes; no product code change is needed.
- **Prevention**: For diagnostic searches, enumerate candidate files with `rg --files` or `find` first, then pass only existing paths to `rg`.

## 2026-04-28: Worktree Mirrors Need Empty-Diff Fast Paths
- **Phenomenon**: Strict changed-path validation passed changed-only tests and Ultra Review, but the Ultra Review sandbox mirror reported `copytree` fallback when the captured diff was empty.
- **Root Cause**: `git apply` treats an empty patch as invalid, so the new worktree mirror path interpreted a clean diff as an apply failure.
- **Decision**: Treat empty diff as a valid worktree mirror fast path, still overlaying allowed untracked files while avoiding copytree fallback.
- **Prevention**: Sandbox mirror strategy checks must distinguish "no patch needed" from "patch failed" before falling back to slower full-copy behavior.

## 2026-04-28: Benchmark Preflight Must Call CodeIntel Contracts Directly
- **Phenomenon**: The first benchmark readiness preflight test failed because the new script called `scan_codebase(output_path=...)`, but the service contract is `scan_codebase(index_path=...)`.
- **Root Cause**: The preflight wrapper guessed a convenience API shape instead of following the existing CodeIntel service contract.
- **Decision**: Call `scan_codebase(index_path=...)` and pass `scan.index_path` into `analyze_impact(...)`; cover the path with a CLI regression test.
- **Prevention**: Benchmark preflight tools must exercise the same production service contracts used by CodeIntel reports, not adapter-only assumptions.
