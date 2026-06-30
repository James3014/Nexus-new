---
status: M1_6_EXISTING_CAPABILITY_REUSE_PLAN_COMPLETE
created: 2026-07-01
scope: plan_only
---

# M1.6 Existing Capability Reuse Plan

## 1. Confirmed Root Cause

M1 benchmark calls `LocalModelExecutor.run()` directly. Depending on `execution_topology`, it takes one of two paths:

**Path A (`localheal_pipeline`)**: `local_model_executor.py:427` → `LocalHealPipelineCapabilityExecutor.execute()` → creates `HealPipeline(ollama_generate_fn=_noop_generate)` but **never calls `HealPipeline.run()`**. The bridge checks module availability and performs lightweight parse, but the pipeline's retry loop, orchestrator, and verification phase are never executed. The `_noop_generate` stub returns `""`, so even if `run()` were called, no model call would occur.

**Path B (`local_committee_only`)**: `local_model_executor.py:320` → `LocalCommitteeCandidateProvider.generate_committee_candidates()` → `_normalize_candidate_patch()` → **returns at line 412**. When `_normalize_candidate_patch` returns empty (due to `REPLACEMENT_MARKDOWN_FENCE`), the committee path commits an empty hash and exits. No path to `isolated_local_solve_loop` or `diff_repair`.

**Consequence**: Neither path reaches `HealOrchestrator._run_repair_loop()` (`orchestrator.py:123`), which contains the `max_tries=3` retry logic and `failure_feedback_builder` integration (`orchestrator.py:139-152`).

---

## 2. Existing Capabilities to Reuse

| # | Capability | File | Lines | Current State |
|---|-----------|------|-------|---------------|
| 1 | `HealPipeline.run()` | `pipeline.py` | 172-217 | Fully implemented. Builds phase list, selects orchestrator, calls `orchestrator.run(v2_ctx)`. Never invoked from M1 path. |
| 2 | `HealOrchestrator._run_repair_loop()` | `orchestrator.py` | 123-216 | `while attempt <= max_tries` loop. Handles patch failure classification, semantic retry, fuzzy healing. Not reached from M1. |
| 3 | `CommitteeOrchestrator` | `pipeline.py:201` | Selected via `NEXUS_USE_COMMITTEE=1`. Has its own orchestrator logic. Not reached from M1. |
| 4 | `build_failure_feedback()` | `failure_feedback_builder.py` | 5-42 | Builds retry feedback prompt with output contract. Connected in orchestrator at `orchestrator.py:139-152` for attempts > 1. Never receives `REPLACEMENT_MARKDOWN_FENCE` error. |
| 5 | `AnchoredEditReplacementGuard` | `protocol.py` | 378-439 | Correctly rejects `REPLACEMENT_MARKDOWN_FENCE`. Guard is working — rejection is correct behavior. |
| 6 | `IsolatedLocalSolveLoop` | `isolated_local_solve_loop.py` | 80-303 | Available. Normalizes diff, runs isolated workspace apply + verifier. Not reached from committee path. |
| 7 | `_normalize_candidate_patch` | `local_model_executor.py` | 673-769 | Returns `("", {...})` on parse failure. Correct behavior — empty hash signals failure. |
| 8 | Orchestrator local backend seam | `orchestrator.py` | 133-152 | `use_local_qwen_backend` flag + `NEXUS_LOCAL_QWEN_BACKEND` env var. Builds failure feedback for retry attempts. |

---

## 3. Seams to Connect

### Seam 1: Bridge → HealPipeline.run() (Path A)

**Current**: `local_model_capability_executors.py:329-331` creates `HealPipeline(ollama_generate_fn=_noop_generate)` but never calls `.run()`.

**Target**: When `execution_topology == "localheal_pipeline"`, the bridge should invoke `HealPipeline.run(heal_context)` with a real `ollama_generate_fn` (the provider's `generate()` method), not `_noop_generate`.

**Key question**: Where does the real `ollama_generate_fn` come from? The `LocalModelExecutor.run()` receives a `provider: LocalModelProvider | None` parameter. The bridge needs access to this provider's `generate()` method.

**Files to change**: `local_model_capability_executors.py` (bridge execute method)
**Seam point**: `local_model_capability_executors.py:329-331`

### Seam 2: Committee parse failure → retry feedback (Path B)

**Current**: `_normalize_candidate_patch()` returns `("", {"protocol_parse_failed": True, "error_kind": "REPLACEMENT_MARKDOWN_FENCE"})` → candidate gets empty hash → committee returns at line 412.

**Target**: When `_normalize_candidate_patch` returns empty due to `REPLACEMENT_MARKDOWN_FENCE`, instead of treating it as terminal, build a `failure_feedback` message and feed it into the next retry iteration. The feedback should instruct: "Your previous patch was wrapped in markdown fences. Output ONLY raw code inside REPLACE block. No markdown fences."

**Key question**: The committee path in `LocalModelExecutor.run()` is single-shot (line 320-412). To add retry, we need either:
- (a) Wrap the committee call in a retry loop within `LocalModelExecutor.run()`, or
- (b) Route committee failures through `HealPipeline` which already has retry.

Option (b) is cleaner — it reuses existing retry infrastructure.

**Files to change**: `local_model_executor.py` (committee path), `failure_feedback_builder.py` (add fence-specific instruction)
**Seam points**: `local_model_executor.py:348-412`, `failure_feedback_builder.py:5-42`

### Seam 3: REPLACEMENT_MARKDOWN_FENCE → failure_feedback_builder

**Current**: `failure_feedback_builder.build_failure_feedback()` accepts `failure_class` string. The orchestrator passes it at `orchestrator.py:139-152` with the classified failure. But `REPLACEMENT_MARKDOWN_FENCE` never reaches this path.

**Target**: Extend `failure_feedback_builder` to recognize `REPLACEMENT_MARKDOWN_FENCE` failure class and include a fence-stripping instruction in the output contract.

**Files to change**: `failure_feedback_builder.py`
**Seam point**: `failure_feedback_builder.py:28-41` (feedback template)

### Seam 4: Orchestrator → local provider (retry model call)

**Current**: `orchestrator.py:157-166` calls `backend.generate_patch(...)` for local backend retry. This already works for the local qwen backend path.

**Target**: Ensure the local provider's `generate()` method is wired through `HealPipeline.__init__` so the orchestrator can call it during retry.

**Files to change**: `pipeline.py` (ensure `ollama_generate_fn` is real, not `_noop`)
**Seam point**: `pipeline.py:146-157`

---

## 4. Forbidden Duplicate Work

| Forbidden | Rationale |
|-----------|-----------|
| New parser | `SolidSearchReplaceProtocol` is correct. Fence rejection is correct behavior. |
| New sanitizer | `SearchReplaceParser._clean_content` already strips fences for legacy. Not for anchored_edit. |
| New route/topology | Existing `localheal_pipeline` and `local_committee_only` topologies are sufficient. |
| Relaxed verifier | `AnchoredEditReplacementGuard` is working as designed. |
| Relaxed candidate isolation | `IsolatedLocalSolveLoop` isolation is correct. |
| Fake solved pass | Empty hash must remain `solved=false`. |
| Modifying `AnchoredEditReplacementGuard` | Defense-in-depth fence checks are correct. |
| Modifying `SearchReplaceParser._clean_content` for anchored_edit | Legacy path must not leak into anchored_edit. |

---

## 5. Staged Implementation Sequence

### Stage 1: Wire bridge to call HealPipeline.run() with real provider

**Goal**: Make `localheal_pipeline` topology actually execute the full pipeline.

**What changes**:
- `local_model_capability_executors.py:329-331`: Replace `_noop_generate` with a closure over the real provider's `generate()` method. The bridge's `execute()` method needs to accept the provider (or receive it via context).
- `local_model_capability_executors.py:202` (execute signature): Add `provider` parameter or extract from `ctx`.
- `local_model_executor.py:438`: Pass `provider` to `LocalHealPipelineCapabilityExecutor().execute(cap_ctx, provider=provider)`.

**Tests required**:
- `test_bridge_calls_heal_pipeline_run` — mock `HealPipeline.run`, verify it's called (not just instantiated)
- `test_bridge_uses_real_provider_not_noop` — verify `ollama_generate_fn` is not the `_noop_generate`
- `test_bridge_returns_pipeline_result` — verify `CapabilityExecutionResult` includes pipeline output

**Rollback criteria**: If `HealPipeline.run()` raises or produces worse results than bridge-only, revert bridge to `_noop_generate` and log the failure. The bridge-only path is the current baseline — any regression in solved rate or error rate triggers rollback.

---

### Stage 2: Connect REPLACEMENT_MARKDOWN_FENCE to failure_feedback_builder

**Goal**: When fence rejection occurs, the retry prompt explicitly instructs the model to not use fences.

**What changes**:
- `failure_feedback_builder.py:28-41`: Add `REPLACEMENT_MARKDOWN_FENCE` to the recognized `failure_class` values. When this class is detected, append to the output contract: "IMPORTANT: Do NOT wrap your code in markdown fences (```...```). Output ONLY raw code inside REPLACE block."
- `orchestrator.py:139-152`: Ensure `REPLACEMENT_MARKDOWN_FENCE` is passed as `failure_class` when the patch phase fails with this error kind.

**Tests required**:
- `test_failure_feedback_includes_fence_instruction` — when `failure_class="REPLACEMENT_MARKDOWN_FENCE"`, feedback string contains fence-specific instruction
- `test_failure_feedback_other_classes_unchanged` — other failure classes produce unchanged feedback

**Rollback criteria**: If the fence instruction causes the model to produce worse output (e.g., strips fences but introduces prose contamination), revert to generic feedback.

---

### Stage 3: Route committee parse failure through pipeline retry

**Goal**: Committee path with `REPLACEMENT_MARKDOWN_FENCE` should retry via `HealPipeline` instead of returning empty hash at line 412.

**What changes**:
- `local_model_executor.py:348-412`: After `_normalize_candidate_patch` returns empty, check if `error_kind == "REPLACEMENT_MARKDOWN_FENCE"`. If so, instead of committing empty hash and returning, build `failure_feedback` and re-invoke the committee with the feedback appended to the prompt.
- Alternative (cleaner): Route the entire committee failure through `HealPipeline.run()` which already handles retry. This requires the `local_committee_only` topology to fall back to `localheal_pipeline` on parse failure.

**Tests required**:
- `test_committee_fence_failure_retries_with_feedback` — committee path with fenced output retries and includes fence instruction
- `test_committee_non_fence_failure_still_returns_empty` — non-fence parse failures (e.g., `empty_patch`) still return empty hash immediately
- `test_committee_retry_exhaustion_returns_empty` — after max retries, returns empty hash (no false positive)

**Rollback criteria**: If committee retry produces false-positive solves (patch applied but wrong), revert to immediate return. The empty-hash path is the safe baseline.

---

### Stage 4: Verify with M1 benchmark re-run

**Goal**: Confirm the staged changes improve M1 benchmark results without regressions.

**What to measure**:
- Solved rate (target: >0, baseline was 0/6 for fenced tasks)
- Error rate (must not increase)
- Retry count distribution (should show retries happening)
- No false positives (solved=true with wrong patch)

**Tests required**:
- Re-run `scripts/bench/m1_real_local_solve_benchmark.py`
- Compare results to M1 baseline (from `m1_real_local_solve_summary.md`)

**Rollback criteria**: If solved rate doesn't improve OR error rate increases, revert Stages 1-3 incrementally to isolate which stage introduced the regression.

---

## 6. Required Tests Summary

| Stage | Test | Type | Assertion |
|-------|------|------|-----------|
| 1 | `test_bridge_calls_heal_pipeline_run` | Unit | `HealPipeline.run` called (mock) |
| 1 | `test_bridge_uses_real_provider` | Unit | `ollama_generate_fn` is not `_noop_generate` |
| 1 | `test_bridge_returns_pipeline_result` | Unit | Result includes pipeline output fields |
| 2 | `test_failure_feedback_includes_fence_instruction` | Unit | Feedback contains fence instruction when class=`REPLACEMENT_MARKDOWN_FENCE` |
| 2 | `test_failure_feedback_other_classes_unchanged` | Unit | Other classes produce unchanged feedback |
| 3 | `test_committee_fence_failure_retries` | Unit | Committee retries with feedback on fence failure |
| 3 | `test_committee_non_fence_failure_still_returns_empty` | Unit | Non-fence failures return empty immediately |
| 3 | `test_committee_retry_exhaustion_returns_empty` | Unit | After max retries, returns empty hash |
| 4 | `test_m1_benchmark_re_run` | Integration | Benchmark results meet criteria |

---

## 7. Rollback Criteria

| Trigger | Action |
|---------|--------|
| `HealPipeline.run()` raises exception in bridge | Revert Stage 1 (bridge back to `_noop_generate`) |
| Solved rate decreases from baseline | Revert last staged change |
| Error rate increases | Revert last staged change |
| False positive detected (solved=true, wrong patch) | Revert Stage 3 (committee retry) |
| Fence instruction causes prose contamination | Revert Stage 2 (generic feedback) |
| Any existing test fails | Fix before proceeding to next stage |

---

## 8. Execution Dependencies

```
Stage 1 (bridge → pipeline)
    ↓
Stage 2 (feedback → fence instruction)  [can run in parallel with Stage 1]
    ↓
Stage 3 (committee → retry)  [depends on Stage 2 for feedback]
    ↓
Stage 4 (benchmark verification)  [depends on all above]
```

---

## 9. Key Code Locations Reference

| Component | File | Lines |
|-----------|------|-------|
| M1 benchmark entry | `scripts/bench/m1_real_local_solve_benchmark.py` | 33-430 |
| `LocalModelExecutor.run()` | `nexus/services/local_heal/local_model_executor.py` | 116-769 |
| Committee path | `local_model_executor.py` | 317-412 |
| Pipeline topology branch | `local_model_executor.py` | 427-479 |
| `_normalize_candidate_patch` | `local_model_executor.py` | 673-769 |
| Bridge class | `nexus/services/local_heal/local_model_capability_executors.py` | 192-374 |
| Bridge `_noop_generate` | `local_model_capability_executors.py` | 329 |
| Bridge `HealPipeline(...)` | `local_model_capability_executors.py` | 331 |
| `HealPipeline.run()` | `nexus/services/local_heal/pipeline.py` | 172-217 |
| `HealPipeline.__init__` | `pipeline.py` | 146-157 |
| Orchestrator selection | `pipeline.py` | 201 |
| `HealOrchestrator._run_repair_loop` | `nexus/services/local_heal/orchestrator.py` | 123-216 |
| Orchestrator local backend seam | `orchestrator.py` | 133-152 |
| `build_failure_feedback` | `nexus/services/local_heal/failure_feedback_builder.py` | 5-42 |
| Feedback template | `failure_feedback_builder.py` | 28-41 |
| `AnchoredEditReplacementGuard` | `nexus/services/local_heal/protocol.py` | 378-439 |
| `IsolatedLocalSolveLoop` | `nexus/services/local_heal/isolated_local_solve_loop.py` | 80-303 |
