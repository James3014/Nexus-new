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
- Current scope: Python import reverse-impact only; no full symbol graph, no watch/index daemon, no external runtime.

Lesson:
- CodeIntel should start with a small, deterministic stdlib path. A conservative import-impact result is more useful for gates than a broad opaque graph that cannot be explained or tested.
- Impact scanning must exclude generated sandboxes and local caches such as `.nexus`, `.git`, `.venv`, and `.codex`; otherwise stale review worktrees inflate blast radius and make the evidence unusable.

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

Lesson:
- Existing fixtures with placeholder `file1.py` become real code-change tasks once code-impact is fail-closed. Tests that are not about code changes should use docs paths; code-change pass tests must include `nexus code:impact` evidence.

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
- Still not default-on production; the missing production step is rollout policy: which task classes may enable the flag, and what CI gate requires when RLM is used.

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

## Lesson

- 跨 worktree 文件可能存在於 `/Users/jameschen/Workspace/nexus`，但主工作區是 `/Users/jameschen/.codex/worktrees/ad59/nexus`。執行前要用絕對路徑確認，避免把另一份工作區的計劃誤判為本 worktree 已落地。
- P28 已有比原計劃更多的實作；後續應先查現況再開發，避免重複建置。
