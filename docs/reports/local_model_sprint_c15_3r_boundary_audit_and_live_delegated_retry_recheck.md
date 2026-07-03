# Local Model Sprint C15-3R: Boundary Audit and Live Delegated Retry Recheck

## 1. MCP / Git Audit Evidence

**HEAD verified by MCP prior to sprint:**
```
a0b84d1d2 feat(localheal): implement C15-3Q delegated retry empty response diagnostics and fix phase key match bug
```

**C15-3Q changed files (6 total, confirmed via `git show --stat`):**
```
docs/reports/local_model_sprint_c15_3q_delegated_retry_empty_response_root_cause.md
nexus/services/local_heal/local_model_capability_executors.py
nexus/services/local_heal/local_model_executor.py
nexus/services/local_heal/orchestrator.py
scripts/bench/m1_real_local_solve_benchmark.py
tests/unit/local_heal/test_retry_metadata.py
```

Note: `tests/unit/local_heal/test_local_model_executor.py` is a *verification* test file — it was run during C15-3Q but was NOT modified by the C15-3Q commit.

---

## 2. Dirty Tree Hygiene Warning

`git status --short` shows the following files that MUST NOT be staged in the next commit:

```
M  .nexus/reports/learn/learning_closure.jsonl
M  .serena/project.yml
?? artifacts/external_sources/sympy_13852
M  artifacts/runtime/**/*.json          (multiple runtime benchmark results)
M  nexus/**/__pycache__/*.pyc           (multiple compiled Python cache files)
M  nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md
M  tests/unit/**/__pycache__/*.pyc
?? codebase-memory-mcp
?? docs/reports/local_model_sprint_c15_3f_bounded_live_validation_after_verifier_receipt_fix.md
?? docs/research/nexus-knowledge-agent-integration.md
```

These are excluded from the C15-3R commit. Only the report is staged.

---

## 3. Boundary Audit Table

All 12 red-line checks verified via `git show --no-ext-diff --unified=15 a0b84d1d2` on the three executor/orchestrator files.

| # | Boundary Check | Result | Evidence |
|---|---|---|---|
| 1 | `CapabilityPlanner` not modified | **YES** | Not in C15-3Q changed file list; `git show` confirms no diff in `nexus/engine/capability_planner.py` |
| 2 | `HybridRouteDecision` not modified | **YES** | Not in C15-3Q changed file list; no diff in `nexus/contracts/hybrid_route.py` |
| 3 | No new route / router / planner / topology selector added | **YES** | Diff shows only telemetry writes and diagnostic field collection; no route logic added |
| 4 | No new `execution_topology` string added | **YES** | No new topology enum or string constant in any diff hunk |
| 5 | No new env-driven route branch added | **YES** | No `os.environ` or env-gated branch in diff |
| 6 | No new retry loop added | **YES** | `_attempt_semantic_retry` was refactored for telemetry only; no loop structure added |
| 7 | Verifier behavior not modified | **YES** | `phase_runner.run_phase(self.verify_phase, ...)` call unchanged; no `EvaluationGate` diff |
| 8 | Parser contract not modified | **YES** | `SolidSearchReplaceProtocol` instantiation and call unchanged; only `.kind.name` read for telemetry |
| 9 | Candidate isolation behavior not modified | **YES** | No diff in `candidate_isolation_gate.py`; isolation logic untouched |
| 10 | No hardcode toy solution | **YES** | No task-id branch, no hardcoded value targeting `toy-math-solve` |
| 11 | C15-3Q report does not claim `solved` / `local_armor_ready` / `production_ready` / `public_claim_allowed` | **YES** | Live validation row in report explicitly shows `Outcome: FAILED`; conclusion limited to "diagnostics closed" |
| 12 | Dirty tree not mixed into next commit | **YES** | Only `docs/reports/local_model_sprint_c15_3r_*.md` staged |

All 12 red-line checks: **PASS**.

---

## 4. Deterministic Test Evidence

**Python compilation check (7 files):**
```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/local_model_executor.py \
  nexus/services/local_heal/orchestrator.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_retry_metadata.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py
# Result: exit code 0, no output (all files compile cleanly)
```

**Focused pytest (3 test files):**
```bash
uv run pytest \
  tests/unit/local_heal/test_retry_metadata.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py -q
# Result: 162 passed in 1.91s
```

Test breakdown: 14 (test_retry_metadata) + 140 (test_local_model_executor) + 8 (test_m1_real_local_solve_benchmark) = **162 passed**.

---

## 5. Live Matrix Rows Summary (3/5 runs — pattern stable at 3)

| Run | patch_lifecycle_state | failure_class | apply_failure_root_cause | hash_match | retry_eligible | pipeline_retry_delegated | semantic_retry_invoked | semantic_retry_invocation_source | semantic_retry_prompt_len | semantic_retry_response_empty | semantic_retry_output_class | semantic_retry_status | verifier_result | solved | duration |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | isolation_attempted_apply_failed | patch_apply_failed | search_block_mismatch_current_source | False | False | **False** | True | orchestrator_semantic_retry | 1088 | False | VALID_PATCH | VERIFIER_FAILED | fail | False | 69.2s |
| 2 | isolation_attempted_apply_failed | patch_apply_failed | search_block_mismatch_current_source | False | False | **False** | True | orchestrator_semantic_retry | 1088 | False | VALID_PATCH | VERIFIER_FAILED | fail | False | 50.0s |
| 3 | isolation_attempted_apply_failed | patch_apply_failed | search_block_mismatch_current_source | False | False | **False** | True | orchestrator_semantic_retry | 1194 | False | VALID_PATCH | VERIFIER_FAILED | fail | False | 71.3s |

**Stable pattern across 3 runs (no variance). Additional runs not required.**

### Key Findings

1. **Delegated retry branch structurally unreachable for this task**: `pipeline_retry_delegated=False` in all 3 runs. The eligibility gate requires `hash_match=True` AND `candidate_isolated=True`. Both are `False` because the primary patch fails at apply time (search block mismatch) before any candidate can be isolated or verified.

2. **Orchestrator's own semantic retry IS firing**: `semantic_retry_invoked=True` with `invocation_source=orchestrator_semantic_retry`. The LLM responds with a non-empty string (prompt_len ≥ 1088, response_empty=False, output_class=VALID_PATCH). The parser accepts the patch. But the verifier still fails after the retry.

3. **C15-3Q diagnostics correctly populated**: All 15 diagnostic fields carry live values (non-default) for the orchestrator semantic retry path. The telemetry implementation is correct.

4. **The delegated retry diagnostics (C15-3P scope) cannot be exercised** until the primary pipeline achieves `hash_match=True` — i.e., candidate isolation must succeed first.

---

## 6. Decision Gate Result

Evaluating against C15-3R decision gates:

| Gate | Condition | Status |
|---|---|---|
| A | `verifier_result=pass` AND `solved=true` | ❌ Not met |
| B | `pipeline_retry_delegated=True` + `prompt_has_verifier_evidence=True` + `response_empty=True` | ❌ Delegated branch never fires |
| C | `pipeline_retry_delegated=True` + `prompt_has_verifier_evidence=False` | ❌ Delegated branch never fires |
| D | `pipeline_retry_delegated=True` + diagnostics still default | ❌ Delegated branch never fires |
| **E** | **≥3 runs majority: patch apply failed / search_block_mismatch** | ✅ **3/3 confirmed** |
| F | response non-empty but parser/protocol fail | ❌ VALID_PATCH (parser accepts) |

**Gate E fires.** The delegated retry branch is structurally gated behind candidate isolation, which itself requires escaping the `search_block_mismatch_current_source` primary failure mode.

---

## 7. Next Task Recommendation

**→ C15-3S: Reanchor / Locked Search Stability Follow-up**

Root constraint: `apply_failure_root_cause=search_block_mismatch_current_source` with `hash_match=False` prevents candidate isolation, which blocks `retry_eligible` and therefore `pipeline_retry_delegated`.

The C15-3S task should focus on:
1. Diagnosing why the locked search span does not match the current source.
2. Auditing `reanchor` logic and `pipeline_locked_search_reanchored` flag.
3. Determining if the search block mismatch is due to source drift, projection error, or LLM-generated SEARCH that diverges from canonical.
4. **Not** modifying CapabilityPlanner, HybridRouteDecision, verifier, or parser.
5. **Not** claiming solved unless `verifier_result=pass` AND `solved=True` is empirically confirmed.

---

## 8. Non-Claims

```
not solved — verifier_result=fail in all 3 live runs
not local_armor_ready
not production_ready
not public_claim_allowed
```

C15-3Q diagnostics closure is confirmed. Delegated retry branch closure is **not confirmed** — the branch is structurally unreachable at current primary pipeline failure mode.
