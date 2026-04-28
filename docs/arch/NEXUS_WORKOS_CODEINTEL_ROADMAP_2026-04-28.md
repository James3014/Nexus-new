# Nexus Work OS / CodeIntel Roadmap

日期：2026-04-28

## 目標

把 Nexus 已有的治理、證據、RLM、benchmark 能力，收斂成可產品化的 Work OS 與原生 CodeIntel 主路徑。外部 GitNexus / SocratiCode 只作能力對標，不引入外部 runtime、daemon、DB 或套件。

## P28: RLM 內化狀態

What:
- RLM trace / budget contract、RecursiveRepairLoop、RLM benchmark trace evidence 已存在。
- 本輪不重做，避免把已完成能力當新功能重寫。

Why:
- Nexus 的 RLM 價值在於「治理內迴圈」，不是自由 agent。
- 已有 trace/budget/submission semantics 後，下一步應接 rule lifecycle 與 Work OS gate。

How:
- 保留 feature flag 行為。
- 後續只補 per-iteration MemPalace / Belief / CapabilityGate policy 與 harder benchmark。

## P29: 自我更新 Rule Lifecycle

What:
- 新增 rule lifecycle contract：`active | light | deprecated | removed_candidate`。
- 用 verified lift、trust mismatch、cost delta、sample size 決定規則是否保留或降摩擦。

Why:
- Nexus 不能變成靜態規則堆疊。模型變強時，低收益高成本規則應降級；仍能降低幻覺/風險的規則要保留。

How:
- `RuleLifecycleEvidence` 記錄每條治理規則的 benchmark 證據。
- `recommend_rule_state()` 先用保守、可解釋規則，不急著 ML。

## P30: Work OS Contract 最小落地

What:
- Task contract 補 `consulted_agents <= 2`、`delivery_profile`、`requires_proposal/proposal_ref`。
- live delivery profile 需要 human-approval evidence。
- code-change path 開始有 `code-impact` evidence kind / requirement。

Why:
- 這把文件中的 Work OS 規則變成程式級 fail-closed contract：單一 owner、最多兩位 consulted、live/mock 不可混淆、跨邊界任務要 proposal。

How:
- 先在 orchestrator task layer 落地，不改 CLI 與 delivery runtime。
- 下一刀接到 `nexus/delivery/models.py`、`nexus/delivery/gate.py`、`scripts/ops/closeout_guard.py`，讓 closeout 與 completion gate 也使用同一份 contract。

Status:
- 2026-04-28 P30a implemented in orchestrator task contract.
- 2026-04-28 P30b implemented in delivery completion gate, task runner pass-through, and closeout guard.

Lesson:
- `delivery_profile=live_*` is an extra governance requirement, not a shortcut around existing task-level verification floors. Live delivery must satisfy both the normal command/artifact contract and live evidence / human approval policy.

## P31: Native CodeIntel Convergence

What:
- 新增 Nexus 原生 code intelligence 主路徑：
  - `nexus code:scan`
  - `nexus code:impact --files ...`
  - `nexus code:context --symbol ...`
- 新增內建 service：
  - `nexus/services/codeintel/models.py`
  - `graph_builder.py`
  - `impact_service.py`
  - `context_service.py`

Why:
- Nexus 強在治理與 evidence，但 code-intel 目前仍是分散原型。要做到「放心交付」，code-change 任務必須先有 impact/context 證據。

How:
- 借鏡 GitNexus 的 graph-first / impact / symbol context 設計。
- 借鏡 SocratiCode 的 CLI/status/UX 產品化模式。
- 不引入外部專案，不接外部服務；只把 repo 內既有原型收斂成內建 service。

Status:
- 2026-04-28 P31a implemented: native `code:impact` service and CLI.
- 2026-04-28 P31b implemented: native `code:scan` graph builder and CLI.
- 2026-04-28 P31c implemented: native `code:context` service and CLI.
- Current scope: Python module/import graph only; no watch/index daemon, no external runtime.

Lesson:
- CodeIntel should start with a small, deterministic stdlib path. A conservative import-impact result is more useful for gates than a broad opaque graph that cannot be explained or tested.
- Impact scanning must exclude generated sandboxes and local caches such as `.nexus`, `.git`, `.venv`, and `.codex`; otherwise stale review worktrees inflate blast radius and make the evidence unusable.
- Scan output should be a deterministic graph index plus a small scan report. Keep indexing local and explainable before adding watch mode or richer symbol extraction.
- Context output is currently module/import context. It is ready for gate evidence, but not yet a full symbol-level IDE index.

## P32: CodeIntel Gate / Multi-Agent 接線

What:
- code-change 任務缺 `code-impact` evidence 時 gate fail-closed。
- owner 仍唯一；codeintel analyst 與 guardrail reviewer 只能作 consulted evidence producer / reviewer。

Why:
- CodeIntel 不只是查詢工具，而是 A/C gate 的前置證據。這能降低 blind patch、漏測與跨模組回歸。

How:
- 擴充 task/evidence policy。
- 接 `delivery-gate` 與 closeout guard。
- 加 e2e：`code:scan -> code:impact -> patch evidence -> delivery gate`。

Status:
- 2026-04-28 P32a implemented: code-change tasks require `code-impact` evidence at pre-gate even when the task did not explicitly list it.
- 2026-04-28 P32b implemented: `code:impact` emits `report_path` and includes the report in `evidence_paths`, making it easier for gates and closeout bundles to cite the same artifact.
- 2026-04-28 P32c implemented: pre-gate accepts code-impact only when a readable `codeintel-v1` report artifact is present.
- 2026-04-28 P32c e2e verified: real CodeIntel impact report can satisfy `verify_gate`.
- 2026-04-28 P32d implemented: `code:impact --index-path` can consume the deterministic graph emitted by `code:scan`, so the product path is now `scan -> impact` instead of two unrelated commands.
- 2026-04-28 P32e implemented: code-change pre-gate and claim bundles now require both readable `code-scan` and `code-impact` `codeintel-v1` reports. Evidence bundles expose `codeintel_artifacts.scan_reports`, `impact_reports`, and validity flags.

Lesson:
- Existing fixtures with placeholder `file1.py` become real code-change tasks once code-impact is fail-closed. Tests that are not about code changes should use docs paths; code-change pass tests must include `nexus code:impact` evidence.
- CodeIntel evidence must include the generated report path, not just changed source files. Otherwise a task can claim impact analysis happened without a reusable artifact.
- CLI spelling varies between click command words (`code impact`) and product wording (`code:impact`). Evidence inference accepts both forms.
- CodeIntel scan indexes should be reusable evidence, not a side artifact. Impact reports now record `scan_index_used` and cite the index path so downstream gates can audit the full chain.
- Claim derivation must use full claim requirements, while pre-gate may defer A/C-only requirements. Otherwise a task can be safe to enter delivery-gate but still not safe to claim `VERIFIED`.

## P33: RLM Production Hardening

What:
- RLM repair loop remains feature-flagged, but each iteration is already governed by CapabilityGate, MemPalace, and Belief.

Why:
- This keeps RLM as a Nexus-governed inner loop instead of a free-running agent.

How:
- `RecursiveRepairLoop.prepare_iteration()` computes allowed tools, belief confidence, MemPalace audit, and policy block trace before repair execution.
- Low belief confidence removes write tools.
- MemPalace denial records `policy_blocked` and fails closed before repair.

Status:
- 2026-04-28 verified by `tests/engine/test_recursive_repair_loop.py`.
- 2026-04-28 P33b added rollout policy for disabled / trace-only / repair-loop / research-loop-candidate modes.
- Still not default-on production; the remaining production step is enforcing the required gates in CI and benchmark reports.

Upgrade ladder:
1. P33c: make RLM reports fail closed when required gates are missing: `rlm_trace_present`, `submit_not_success`, `ac_gate_verified`.
2. P33d: add trace-quality scoring: iteration count, submit count, verified count, policy block count, evidence density, and budget exhaustion.
3. P33e: compare `Nexus RLM-off` vs `Nexus RLM-on` on harder tasks before claiming RLM lift.
4. P33f: keep live delivery disabled unless metadata explicitly allows it.

Lesson:
- RLM hardening should be measured as policy compliance and trace quality, not only solve rate. `SUBMIT` must remain a handoff to A gate, never a success claim.

## P34: X-Phase Recursive Research Loop

What:
- Research auto-flow already emits RLM trace when `NEXUS_RLM_REPAIR_LOOP=1`.

Why:
- Benchmark product paths often enter through `research:auto-flow`, so RLM evidence must be visible there even when the lower pipeline repair loop is not the direct execution path.

How:
- Current bridge writes R/A trace events from research result and artifact verification.
- Full recursive research remains future work: iterative hypotheses, evidence scoring, winner reason, and budgeted X-loop.

Status:
- 2026-04-28 P34a verified as trace bridge, not full recursive X-loop.
- P34b remains: implement budgeted recursive research iterations with MemPalace/Belief/CapabilityGate per iteration.

Upgrade ladder:
1. P34b: implement a governed `RecursiveResearchLoop` behind an explicit flag.
2. P34c: emit multi-event X traces: candidate generated, evidence scored, candidate rejected, winner selected, budget exhausted.
3. P34d: connect X trace to Learn/Ask learning closure without duplicate writeback.
4. P34e: require X-loop budget evidence before public reports may claim recursive research.

Lesson:
- A trace bridge is enough for observability and benchmark evidence, but not enough to claim full RLM research recursion. Public reports should say `RLM trace present`, not `recursive research solved`.

## Cross-Cutting Cleanup

Status:
- 2026-04-28 policy memory path standardized on `.nexus/knowledge/policy_memory.jsonl`.
- 2026-04-28 Ask rerank duplicate repo-boost / drift-suppression pass removed.

Lesson:
- Path aliases such as `policy_memory.jsonl` versus `policymemory.jsonl` split learning evidence. Canonical storage paths should live in one helper and tests must assert the canonical name.
- Rerank stages should be single-pass and ordered. Applying repo boost / drift suppression twice makes answer source weighting harder to explain and can hide topic-pack problems.

## P35: Self-Updating Meta-Framework

What:
- Benchmark comparison now emits rule lifecycle recommendations.

Why:
- Nexus needs to learn which governance rules still earn their cost as models improve.

How:
- `scripts/bench/ab_eval.py` converts A/B deltas into `RuleLifecycleEvidence`.
- Current rules: `verified-delivery-governance`, `rlm-trace`.
- Recommendation remains conservative and explainable: `active | light | deprecated | removed_candidate`.

Status:
- 2026-04-28 P35a implemented in benchmark evaluation output.

Lesson:
- Rule lifecycle must start as advice, not automatic deletion. Public benchmark output can recommend demotion, but production rule changes still need review.

## P36: Benchmark Skill Formalization

What:
- Continuous optimization skill now requires before/after comparisons, RLM on/off comparisons, and rule lifecycle output.

Why:
- Future Nexus optimization needs repeatable evidence, not one-off benchmark stories.

How:
- Skill requires stable model/task/verifier/eligibility across runs.
- RLM-specific runs must compare bare, Nexus RLM-off, and Nexus RLM-on.

Status:
- 2026-04-28 P36a implemented in `.agents/skills/nexus-benchmark-continuous-optimization/SKILL.md`.

Lesson:
- Benchmark workflows are part of the product. If the skill does not force stable denominators and model identity, reports can drift into marketing instead of evidence.

## P37: JIT v5 Data Feedback

What:
- JIT has moved past static mapping into observation mode, but not ML mode.

Why:
- Full test growth requires affected-test selection, but missed tests are more dangerous than slow tests. Nexus should collect explainable evidence before predictive ranking.

How:
- Current selector emits confidence, risk, sources, unmatched paths, fallback usage, high-risk escalation, risk reasons, retry recommendations, and history stats.
- Current CI writes changed-only selection evidence and JIT observations.
- Coverage gap report identifies fallback-heavy or high-risk gaps.

Status:
- 2026-04-28 P37a considered complete as observation/data-feedback foundation.
- 2026-04-28 P37b implemented offline nightly `missed_candidate` back-propagation in `scripts/ops/jit_feedback.py`.
- 2026-04-28 P37c implemented `.nexus/test_impact_stats.json` generation with per-target score inputs.
- 2026-04-28 P37d implemented selector `--ranking static|predictive`; default remains `static`.
- 2026-04-28 P37e implemented `scripts/ops/jit_promotion.py` and `ci_gate.py --jit-promotion-report`; promotion remains warn-only and default ranking remains `static`.
- 2026-04-28 P37f clarified promotion boundary: `PROMOTE_CANDIDATE` can enter trial lane only; default switch stays blocked until a sustained observation window passes.

Upgrade ladder:
1. P37e: generate a promotion report that compares predictive ranking against static using miss-rate, fallback-rate, unmatched paths, nightly full-run count, and saved-runtime estimate.
2. P37f: keep predictive ranking as warn-only until the promotion report says `PROMOTE_CANDIDATE`.
3. P37g: add a trial lane in CI that runs predictive selection as analysis while static remains authoritative.
4. P37h: only after 2-4 weeks of clean observation, consider switching selected low-risk paths from static to predictive.

Meta-style target:
- Nexus JIT should converge toward affected tests + dependency graph + historical co-failure + flaky/duration cost + nightly miss calibration.
- Nexus should not claim Meta-scale JIT until it has distributed execution, large historical data, and measured recall against full regression.

Lesson:
- JIT must stay explainable before it becomes predictive. The first product promise is not "ML-selected tests"; it is "we can explain why these tests were selected and where fallback risk remains."
- Predictive ranking is currently an opt-in analysis lane. It is not a public speed or quality claim until nightly miss-rate and saved-runtime evidence are available.

## P38: Public Report Readiness

What:
- Public reporting is now close to candidate-ready, but production-grade claims still require repeated trials and stable evidence bundles.

Why:
- Nexus value should be sold as verified delivery, governance, evidence, cost-aware routing, and traceability. A single benchmark run is not enough for public product claims.

How:
- Required publication gate:
  - same model in both arms
  - eligible denominator excludes infra invalid rows
  - public claim gate PASS
  - raw JSONL + evidence bundle + markdown report
  - Nexus wearing evidence
  - rule lifecycle recommendations
  - RLM trace present when RLM is enabled
  - limitation section with sample size and timeout policy

Status:
- 2026-04-28 P38a documented as report readiness gate.
- 2026-04-28 P38b-pre implemented: `capability_ab_runner.py --preflight-only` validates public benchmark inputs without invoking Gemini or Nexus.
- 2026-04-28 P38b-pre verified against `public_benchmark_rlm_harder_v2.json`: 8 tasks x 2 trials, same Gemini 3 Flash model lock, hidden verifier enabled, per-task stop-loss 600s, evidence bundle and markdown report requested.
- 2026-04-28 P38schema added benchmark fields for RLM trace quality, CodeIntel scan/impact claim-bundle presence, and JIT promotion status.
- 2026-04-28 P38rlm-gate added public-claim protection for RLM submit traces: submit must lead to A-gate verified/audit evidence, and recursive X-loop claims require budget evidence.
- 2026-04-28 P39a added RLM X-loop budget summary with iteration, model-call, token, phase-wall, and exhaustion fields.
- 2026-04-28 P39b added RLM trace quality rollup to A/B summaries and public markdown reports.
- 2026-04-28 P39c injected CodeIntel scan/impact evidence into research auto-flow payload and LLM task context.
- Remaining P38b: run 12 tasks x 3 trials for Gemini 3 Flash bare vs Gemini 3 Flash + Nexus after the worktree is clean.
- Remaining P38c: produce Chinese and English public report bundles.
- Remaining P38d: add weekly trend report for verified delivery, trust mismatch, wall time, model calls, and cost per verified success.

Lesson:
- A public Nexus claim must not be "Nexus always wins." The durable claim is narrower and stronger: "same model wearing Nexus delivers more verifiable, auditable outcomes on governance/evidence-heavy tasks under this fixed benchmark."
- Dry preflight should treat missing git status as a warning unless `--require-clean-worktree` is requested. This keeps fixture/unit tests portable while still allowing strict production runs to fail closed.
- Direct Gemini bare mode has multiple internal stages, so per-task timeout must be enforced as a shared deadline, not as separate full budgets for model call and pytest. Otherwise rows can be marked infra-invalid only after wasting quota and wall time.
- Benchmark elapsed-time and timeout budgets must use monotonic time. Wall-clock time can jump during long local runs and corrupt stop-loss, partial-timeout, and public report numbers.

## Benchmark / Launch Readiness Matrix

What:
- Separate engineering gate readiness from public benchmark readiness.

Why:
- Some improvements harden delivery evidence but do not alter Gemini's solving behavior. Rerunning Gemini is expensive and should be reserved for claims about model performance or Nexus treatment behavior.

How:

| Area | Current status | Gemini benchmark required? | Launch standard |
| :--- | :--- | :--- | :--- |
| P30 Work OS gates | Contract + delivery/closeout gate implemented | No | Unit/e2e gates pass; live claims require live evidence + human approval |
| P31 CodeIntel scan/impact/context | Python module/import graph implemented | No, unless injected into Gemini prompt/context or claimed as solve-rate lift | CLI stable, reports reusable, no external deps |
| P32 CodeIntel gate | Code-change pre-gate requires readable `codeintel-v1` report | No for gate claim; yes for "improves Gemini" claim | E2E `code:scan -> code:impact -> verify_gate` pass |
| P33 RLM repair hardening | Feature-flagged R-loop with CapabilityGate/MemPalace/Belief | Yes for RLM value claim | Rollout policy defines allowed task classes and CI requirements |
| P34 X research recursion | Trace bridge only | Yes if claiming recursive research value | Budgeted recursive X-loop implemented and tested |
| P35/P36 benchmark lifecycle | Rule lifecycle + skill workflow implemented | No by itself | Reports include lifecycle recommendations and stable denominators |
| P37 JIT feedback | Observation, missed-candidate backprop, stats, and opt-in predictive ranking implemented | No, unless claiming benchmark speed/value lift | Keep static default; wire feedback into nightly and validate miss-rate before default predictive ranking |
| P38 public report | Candidate-ready only | Yes | 12x3 same-model run, bilingual bundle, public claim gate PASS, trend report |

Lesson:
- "上線" has layers: gate-hardening can ship with unit/e2e proof; public value claims require same-model benchmark evidence; self-optimizing JIT requires multi-week observation before changing defaults.

## Long-Run Execution Order

What:
- Long Gemini and multi-week observation work is intentionally last.

Why:
- It is wasteful to spend Gemini quota or wait for observation windows before the local gates, CodeIntel artifacts, and benchmark interpretation rules are stable.

How:
1. Finish local gate-hardening first: P31/P32 context + report artifact + verify_gate e2e.
2. Run affected tests and targeted CI locally.
3. Only then run Gemini benchmarks:
   - RLM value claim: bare vs Nexus RLM-off vs Nexus RLM-on.
   - Public Nexus claim: Gemini 3 Flash bare vs Gemini 3 Flash + Nexus, 12x3.
4. Let JIT collect observation for 2-4 weeks before switching predictive ranking defaults.

Lesson:
- Expensive evidence should verify a stable product path, not debug a moving implementation.

## Lesson

- 跨 worktree 文件可能存在於 `/Users/jameschen/Workspace/nexus`，但主工作區是 `/Users/jameschen/.codex/worktrees/ad59/nexus`。執行前要用絕對路徑確認，避免把另一份工作區的計劃誤判為本 worktree 已落地。
- P28 已有比原計劃更多的實作；後續應先查現況再開發，避免重複建置。
