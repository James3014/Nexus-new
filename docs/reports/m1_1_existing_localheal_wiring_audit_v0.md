# M1.1 Existing LocalHeal Wiring Audit

- **status**: M1_1_EXISTING_LOCALHEAL_WIRING_AUDIT_COMPLETE
- **date**: 2026-06-30
- **M1 commit inspected**: `9bd3026c1` (add M1 real local solve benchmark suite)
- **Git dirty state**: 15 modified files + 1 untracked dir (artifacts/external_sources/sympy_13852)

---

## 1. M1 Execution Path Trace

### Call Chain

```
m1_real_local_solve_benchmark.py::run_benchmark()
  → _finalize_with_nexus_row(row, provider="ollama", ...)
    → capability_ab_runner constructs row → calls LocalModelExecutor.run(request)
      → _resolve_execution_topology(request)  # reads signal_snapshot.execution_topology
      → build_local_model_provider_from_signal_snapshot()  # OllamaLocalModelProvider
      → source_anchor resolution  # uses locked_search from benchmark spec
      → failure_feedback check  # absent in initial run (no previous_failure)
      → execution_topology branching:
         ├─ "local_committee_only" → LocalCommitteeCandidateProvider → CandidateDecisionAdapter → _normalize_candidate_patch()
         ├─ "local_only" → provider.generate() → _normalize_candidate_patch()
         └─ "localheal_pipeline" → LocalHealPipelineCapabilityExecutor (availability only) → provider.generate() → _normalize_candidate_patch()
      → _normalize_candidate_patch() → SolidSearchReplaceProtocol.parse()
```

### Topology Distribution

| Topology | Tasks |
|---|---|
| `local_committee_only` | astropy__astropy-13236, task-a-real, task-b-real |
| `local_only` | sympy__sympy-13852, concurrency_bug_02 |
| `localheal_pipeline` | toy-math-solve |

---

## 2. 6-Task Result Table

| task_id | topology | local_model_called | candidate_hash | selected_hash | applied_hash | parse_error_kind | diff_repair | same_retry | feedback_used | modules (claimed) | solved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| astropy__astropy-13236 | local_committee_only | true | empty | — | — | REPLACEMENT_MARKDOWN_FENCE | false | 0 | false | CapabilityPlanner, LocalModelExecutor, LocalCommitteeCandidateProvider, CandidateDecisionAdapter, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |
| sympy__sympy-13852 | local_only | true | empty | — | — | REPLACEMENT_MARKDOWN_FENCE | false | 0 | false | CapabilityPlanner, LocalModelExecutor, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |
| concurrency_bug_02 | local_only | true | empty | — | — | REPLACEMENT_MARKDOWN_FENCE | false | 0 | false | CapabilityPlanner, LocalModelExecutor, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |
| toy-math-solve | localheal_pipeline | true | empty | — | — | none | false | 0 | false | CapabilityPlanner, LocalModelExecutor, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |
| task-a-real | local_committee_only | true | empty | — | — | REPLACEMENT_MARKDOWN_FENCE | false | 0 | false | CapabilityPlanner, LocalModelExecutor, LocalCommitteeCandidateProvider, CandidateDecisionAdapter, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |
| task-b-real | local_committee_only | true | empty | — | — | REPLACEMENT_MARKDOWN_FENCE | false | 0 | false | CapabilityPlanner, LocalModelExecutor, LocalCommitteeCandidateProvider, CandidateDecisionAdapter, SolidSearchReplaceProtocol, IsolatedLocalSolveLoop | false |

**Notes on columns:**
- `candidate_hash` = `e3b0c44...` is SHA-256 of empty string (`empty_hash`), meaning parse produced no valid patch.
- `IsolatedLocalSolveLoop` in `modules` is the benchmark's **static enumeration**, not an actual `run_isolated_local_solve_loop()` call.
- All 6 tasks: `candidate_isolated=false`, `verifier_result=fail`, `solved=false`.

---

## 3. Component Matrix

| # | Component | Classification | Evidence |
|---|---|---|---|
| 1 | **SolidSearchReplaceProtocol** | **USED** | Called by `_normalize_candidate_patch()` at `local_model_executor.py:695-700`. Parses `anchored_edit` REPLACE blocks. Fails on 5/6 tasks with `REPLACEMENT_MARKDOWN_FENCE` (qwen wraps output in `` ```python `` fences). toy-math-solve passes parse but produces empty replacement → `no_intents` error. |
| 2 | **SearchReplaceParser** | **NOT_USED** | Legacy parser at `parser.py`. M1 path uses `SolidSearchReplaceProtocol` exclusively. No import of `SearchReplaceParser` in `_normalize_candidate_patch()`. |
| 3 | **_normalize_candidate_patch** | **USED** | Called at `local_model_executor.py:348,529,633`. All 3 topology branches invoke it after model output. Generates unified diff from REPLACE intent. |
| 4 | **canonical_span / ast_boundary** | **NOT_USED** | Benchmark spec provides `locked_search` directly → `source_anchor_source = "locked_search"` for all 6 tasks. `build_local_model_source_anchor()` is only called as fallback when `locked_search` is empty (`local_model_executor.py:238-253`). Never reached. |
| 5 | **diff_normalizer** | **NOT_USED** | Exists at `diff_normalizer.py` and is imported inside `isolated_local_solve_loop.py:86`. M1 path does NOT call `run_isolated_local_solve_loop()`. |
| 6 | **diff_repair** | **NOT_USED** | `repair_malformed_diff()` at `diff_repair.py`. Only called inside `isolated_local_solve_loop.py:178`. M1 path does not reach this. No repair attempted (`diff_repair_attempted=false` on all tasks). |
| 7 | **isolated_local_solve_loop** | **NOT_USED** | `run_isolated_local_solve_loop()` at `isolated_local_solve_loop.py`. M1 path goes through `_finalize_with_nexus_row()` → `LocalModelExecutor.run()` directly. The benchmark's static `execution_path_modules` list includes "IsolatedLocalSolveLoop" but this is a **misleading enumeration**, not actual invocation. |
| 8 | **failure_feedback_builder** | **NOT_USED** | `build_failure_feedback()` at `failure_feedback_builder.py`. In `local_model_executor.py:259-282`, it's only called if `previous_failure` exists in `route_context`. Benchmark provides no `previous_failure` in the initial row. All tasks: `failure_feedback_used=false`. |
| 9 | **same-span retry** | **NOT_USED** | Orchestrator-level retry loop (`orchestrator.py:126`). M1 executes single-pass `_finalize_with_nexus_row()`. `same_span_retry_count=0` on all tasks. |
| 10 | **HealPipeline** | **NOT_USED** | `pipeline.py:HealPipeline.run()`. M1 calls `_finalize_with_nexus_row()` → `LocalModelExecutor.run()`, not `HealPipeline.run()`. For `toy-math-solve` (localheal_pipeline topology), `LocalHealPipelineCapabilityExecutor.execute()` instantiates `HealPipeline` with a `_noop_generate` fn (`local_model_capability_executors.py:331`), but only checks availability — does not run the pipeline. |
| 11 | **Orchestrator** | **NOT_USED** | `orchestrator.py:HealOrchestrator`. Never instantiated in M1 path. The `HealPipeline` instantiation in `LocalHealPipelineCapabilityExecutor` uses a no-op and does not call `orchestrator.run()`. |
| 12 | **candidate isolation gate** | **NOT_USED** | `candidate_isolation_gate.py` is imported in `isolated_local_solve_loop.py`. M1 path does not call `run_isolated_local_solve_loop()`. `candidate_isolated=false` on all tasks. |
| 13 | **verifier** | **PARTIALLY_USED** | Verifier command is passed to `_finalize_with_nexus_row()` but all 6 tasks get `verifier_result=fail`. For most tasks, the verifier never runs because the patch is empty (parse error → empty candidate → `constraint_violation` blocker). |
| 14 | **learning closure** | **NOT_USED** | `learning_closure_written=false` on all tasks. `HealOrchestrator._write_learning_closure()` is only invoked when running through the full orchestrator path. M1 bypasses this entirely. |

---

## 4. Key Findings

### 4.1 M1 Does NOT Exercise Full June LocalHeal Pipeline

The M1 benchmark invokes `LocalModelExecutor.run()` directly via `_finalize_with_nexus_row()`. This path:
- Calls `SolidSearchReplaceProtocol.parse()` for REPLACE block parsing
- Calls `_normalize_candidate_patch()` to convert REPLACE intents to unified diff
- Does NOT go through `HealPipeline.run()`, `HealOrchestrator.run()`, `IsolatedLocalSolveLoop`, or any retry/feedback loop

### 4.2 10 of 14 June Components Are Never Reached

Only 3 components are actually invoked: `SolidSearchReplaceProtocol`, `_normalize_candidate_patch`, and the `LocalCommitteeCandidateProvider` (for committee topology). The remaining 11 components (`SearchReplaceParser`, `canonical_span`, `diff_normalizer`, `diff_repair`, `isolated_local_solve_loop`, `failure_feedback_builder`, `same-span retry`, `HealPipeline`, `Orchestrator`, `candidate isolation gate`, `learning closure`) exist in the June codebase but are completely unreachable from the M1 execution path.

### 4.3 0/6 Solved Is a Wiring/Path Issue, Not Evidence for New Parser

The consistent `REPLACEMENT_MARKDOWN_FENCE` error on 5/6 tasks (and `no_intents` on toy-math-solve) proves that qwen2.5-coder:7b wraps its REPLACE output in markdown fences. The `AnchoredEditReplacementGuard` in `protocol.py:71-79` correctly detects and rejects this. This is a **model output format** problem, not a parser deficiency.

### 4.4 The "IsolatedLocalSolveLoop" Module Listing Is Misleading

The benchmark's `execution_path_modules` list is **statically computed** based on topology (`m1_real_local_solve_benchmark.py:331-336`). It includes "IsolatedLocalSolveLoop" whenever `local_model_called=true`, but `run_isolated_local_solve_loop()` is never actually called. This creates a false impression of pipeline reuse.

### 4.5 No Retry, No Feedback, No Learning

All single-pass. No previous failure context is injected. No learning closure is written. The orchestrator's retry loop, semantic retry, and failure feedback mechanisms are entirely absent from M1.

---

## 5. Conclusion

**M1 does NOT prove full June LocalHeal pipeline reuse.** The 0/6 solved rate is a wiring/path issue (benchmark calls `LocalModelExecutor.run()` directly, bypassing orchestrator, retry loop, diff repair, and learning closure), combined with a model output format issue (markdown fence wrapping). 

**Next action is seam correction, not new feature development.** To exercise existing June capabilities, M1 should either:
1. Route through `HealPipeline.run()` to activate the full orchestrator → repair loop → retry → verification chain, or
2. Wire `_normalize_candidate_patch()` to fall through to `SearchReplaceParser` or add a fence-stripping sanitizer before `SolidSearchReplaceProtocol.parse()`, or
3. Add a `same-span retry` pass after the initial parse failure to let the model self-correct.

---

## 6. Forbidden Claims

- **FORBIDDEN**: "M1 proves the existing LocalHeal pipeline works" — it does not; M1 bypasses 10/14 components
- **FORBIDDEN**: "0/6 means the parser is broken" — 5/6 fail on `REPLACEMENT_MARKDOWN_FENCE` which is a model output format issue, not a parser bug
- **FORBIDDEN**: "SearchReplaceParser is unused by design" — it is unused because M1's `_normalize_candidate_patch()` only calls `SolidSearchReplaceProtocol`, with no fallback to `SearchReplaceParser`
- **FORBIDDEN**: "diff_repair and same-span retry were tested and failed" — they were never invoked
- **FORBIDDEN**: "IsolatedLocalSolveLoop was exercised" — the module list is static enumeration, not actual invocation
