# C15-6G — Local Model Nexus Armor Bounded Preimage Recovery Milestone

This report records the complete execution and gate validation of Google DeepMind's Nexus Armor integration on the local model benchmark substrate, specifically focusing on the toy math solve verification flow.

## 🎯 Verification Claims & Scope Boundaries

### 已證明 (Proven):
- **Toy Task Pipeline End-to-End**: Local Qwen model (`qwen2.5-coder:7b-instruct`) successfully executed end-to-end through the Nexus executor (`localheal_pipeline` topology) / `HealPipeline` / isolated apply sandbox / `micro_verifier` to achieve a complete pass on the `toy-math-solve` task.
- **Executor & Pipeline Wiring**: Resolved dependency mapping (`rank_bm25`) in the local python venv and fixed environmental flags (`NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR=1`) ensuring the runner reaches the local executor pathway correctly.
- **Bounded Preimage Drift Recovery**: Proved that unique-only whitespace and indentation drifts can be deterministic and safely recovered via `DiffToSSRPConverter` without Levenshtein, ignore-all-whitespace, or AST-based fuzzy guessing.
- **Telemetry Observability**: Correctly wired `local_model_called=true`, `selected_candidate_hash_matches_applied=true`, `isolated_apply_status=applied`, and `isolated_verifier_status=pass`.

### 未證明 (Not Proven):
- **Full Product-Level Target**: We cannot claim that Local Model Nexus Armor is fully product-ready or can generalize to production SWE tasks.
- **Real Codebase Benchmark Solves**: Tasks with static verifier evidence gaps (such as `toy-math-verifier-evidence-gap`) or real repository tasks (`astropy`, `sympy`) have not been proven solved.
- **Model Equality**: Local 7B models have not been proven to approach GPT/Gemini-level bare model stability on multi-file complex codebase edits.

---

## 📊 Level-by-Level Validation Matrix

### 🟢 LV0 — Workspace Boundary & Evidence Hygiene
- **What changed**: 
  - `diff_to_ssrp.py`: Implemented unique whitespace/indentation recovery, removing overbroad ignore-all-whitespace fuzzy logic.
  - `orchestrator.py`: Integrated `DiffToSSRPConverter` within semantic retry parse flows.
  - `phases/patch_synthesis.py`: Added relative target file detection logic.
  - `test_diff_to_ssrp.py`: Expanded to 13 strict unit tests.
- **What was verified**: All production changes staged. No unrelated code files modified.
- **What failed**: None.
- **What remains dirty**: Untracked scratch/pycache files only.
- **Is the next level allowed**: YES.

### 🟢 LV1 — Executor Gate Reachability
- **What changed**: Added `NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR=1` to the benchmark environment variables. Corrected row key parsing in `capability_ab_runner.py`.
- **What was verified**: Real local executor path successfully unblocked.
- **Evidence**:
  ```text
  local_model_called (finalized): True
  local_executor_receipt: {'name': 'local_model_executor', 'selected': True, 'invoked': True...}
  ```
- **Is the next level allowed**: YES.

### 🟢 LV2 — Pipeline Reachability and Provider Invocation
- **What changed**: Fixed `_last_provider_diag` scoping in `local_model_capability_executors.py`.
- **What was verified**: Executor successfully triggered `HealPipeline` and invoked the local model provider.
- **Evidence**:
  ```json
  "localheal_pipeline_available": true,
  "localheal_pipeline_instantiated": true,
  "localheal_pipeline_run_called": true,
  "model_called": true,
  "model_name_used": "qwen2.5-coder:7b-instruct",
  "patch_synthesis_prompt_len": 2331,
  "patch_synthesis_output_len": 95
  ```
- **Is the next level allowed**: YES.

### 🟢 LV3 — Candidate Output Understanding
- **What changed**: Integrated solid search/replace classification checks.
- **What was verified**: Local Qwen output was parsed and classified successfully.
- **Evidence**:
  ```json
  "output_class": "VALID_SEARCH_REPLACE",
  "parser_error_kind": "none",
  "contains_search_marker": true,
  "contains_replace_marker": true
  ```
- **Is the next level allowed**: YES.

### 🟢 LV4 — Safe Patch Apply / Bounded Recovery
- **What changed**: Refactored `DiffToSSRPConverter` to enforce strict whitespace/indentation matching rules, rejecting broad fuzzy/ignore-all-whitespace matching.
- **What was verified**: 13 unit tests passed successfully.
- **Evidence**:
  ```text
  pytest tests/unit/local_heal/test_diff_to_ssrp.py: 13 passed in 0.19s
  isolated_apply_status: "applied"
  ```
- **Is the next level allowed**: YES.

### 🟢 LV5 — Single-Candidate Verifier Pass
- **What changed**: Evaluated real-solve patch output on `toy-math-solve`.
- **What was verified**: Candidate successfully verified as pass.
- **Evidence**:
  ```json
  "isolated_verifier_status": "pass",
  "verifier_result": "pass"
  ```
- **Is the next level allowed**: YES.

### 🟢 LV6 — End-to-End Committee Real Solve and Claimable Receipt
- **What changed**: Ran full committee topology on `toy-math-solve`.
- **What was verified**: Real solve successfully verified.
- **Evidence**:
  ```json
  "solved": true,
  "Outcome": "SOLVED",
  "winner_model": "qwen2.5-coder:7b-instruct",
  "duration": 12.07
  ```

---

## 🔬 Real Solve Telemetry Receipt (`toy-math-solve`)
```json
{
  "task_id": "toy-math-solve",
  "execution_topology": "localheal_pipeline",
  "local_model_called": true,
  "candidate_hash": "72c5ffe5af17009b62643f779a058c34b4fa264e09614e388502cfda04b59ce7",
  "applied_patch_hash": "72c5ffe5af17009b62643f779a058c34b4fa264e09614e388502cfda04b59ce7",
  "selected_candidate_hash_matches_applied": true,
  "isolated_apply_status": "applied",
  "isolated_verifier_status": "pass",
  "verifier_result": "pass",
  "solved": true,
  "failure_class": "verifier_passed",
  "actual_model_name_used": "qwen2.5-coder:7b-instruct"
}
```

---

## 🎯 Final Milestone Claim Status

`C15_6G_TOY_REAL_SOLVE_PROVEN_PIPELINE_NOT_PRODUCT_CLAIMABLE`
