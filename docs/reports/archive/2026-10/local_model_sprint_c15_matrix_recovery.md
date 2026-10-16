# C15 Local Model Committee Matrix Recovery Report

- **Status**: `RECOVERY_REPORT_COMPLETED`
- **Date**: 2026-07-05
- **Workspace**: `/Users/jameschen/Workspace/nexus`

---

## 1. Committee Proposer Model Pool (N = 4)

We define the active pool of small local models as:
1. `qwen2.5-coder:7b-instruct` (Safe slug: `qwen2-5-coder-7b-instruct`)
2. `deepseek-coder:6.7b-instruct` (Safe slug: `deepseek-coder-6-7b-instruct`)
3. `ornith:9b` (Safe slug: `ornith-9b`)
4. `qwythos:9b` (Safe slug: `qwythos-9b`)

*Note: `qwen2.5-s2t-advisor:3b` is strictly designated as a judge/advisor and does not belong to the proposer matrix. 14B models and external models are also excluded.*

---

## 2. 10-Combination Matrix Status Recovery

We categorize the 10 combinations of proposer models and their current validated state below:

### Dual Proposer Committee Matrix (6 Combinations)

| Matrix ID | Proposer Combination | Evidential Status | Winner | Solved | Reference Report | Detail / Evidence Status |
|---|---|---|---|---|---|---|
| **A1** | `qwen7b` + `deepseek67b` | **Live Run** | None | `False` | [local_model_sprint_c15_6c_dual_model_live_validation_qwen7b_deepseek67b.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_6c_dual_model_live_validation_qwen7b_deepseek67b.md) | Wiring proof. Output understanding ran; Qwen (Unified Diff Malformed), DeepSeek (Empty Patch). |
| **A2** | `qwen7b` + `ornith9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run A2 in C15-5C. |
| **A3** | `qwen7b` + `qwythos9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run A3 in C15-5C. |
| **A4** | `deepseek67b` + `ornith9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run A4 in C15-5C. |
| **A5** | `deepseek67b` + `qwythos9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run A5 in C15-5C. |
| **A6** | `ornith9b` + `qwythos9b` | **Live Run** | None | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | Wiring proof. Ornith (Apply failed: SEARCH_MISMATCH), Qwythos (Empty Patch). |

### Triple Proposer Committee Matrix (4 Combinations)

| Matrix ID | Proposer Combination | Evidential Status | Winner | Solved | Reference Report | Detail / Evidence Status |
|---|---|---|---|---|---|---|
| **B1** | `qwen7b` + `deepseek67b` + `ornith9b` | **Live Run** | None | `False` | [local_model_sprint_c15_6d_triple_model_live_validation.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_6d_triple_model_live_validation.md) | Wiring proof (Run A). All 3 proposer models executed successfully. Candidate telemetry captured. |
| **B2** | `qwen7b` + `deepseek67b` + `qwythos9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run B2 in C15-5C. |
| **B3** | `qwen7b` + `ornith9b` + `qwythos9b` | **Not Run / Blocked** | N/A | `False` | [local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md) | TIMEOUT/BLOCKED during sequential run B3 in C15-5C. |
| **B4** | `deepseek67b` + `ornith9b` + `qwythos9b` | **Live Run** | None | `False` | [local_model_sprint_c15_6d_triple_model_live_validation.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_sprint_c15_6d_triple_model_live_validation.md) | Wiring proof (Run B). All 3 models returned empty patch / refused outputs. |

### Summary of Recovered Evidence Tiers

- **Live Runs**: 4 Combinations verified live (`A1`, `A6`, `B1`, `B4`).
- **Telemetry Coverage**: Candidate-level execution tracing successfully captured in `delegated_retry_committee_candidates_json`.
- **Solve Proofs**: None. All live runs ended with `solved = False` and either `rejection_reason = "apply_failed: SEARCH_MISMATCH"` or `"patch_empty"`.
- **Wiring Proofs**: Successfully proved that the `local_committee_only` and `localheal_pipeline` topologies correctly distribute model-generation requests to multiple distinct Ollama endpoints sequentially, normalizes results via `output_understanding`, and executes isolated sandboxed runs.

---

## 3. Matrix Runner Audit

We audited the capability structure of the benchmark runner and local-model execution adapter:

### Benchmark script: `scripts/bench/m1_real_local_solve_benchmark.py`
- Parses CLI arguments to override model configurations properly:
  - `--task-id` (Multiple tasks supported)
  - `--executor-model`
  - `--primary-proposer-model`
  - `--secondary-proposer-model`
  - `--judge-model`
  - `--provider-timeout-sec`
  - `--delegated-retry-candidate-models`
- Successfully maps and resolves these overrides, writing them to `signal_snapshot` inside the task execution row context.

### Execution adapter files:
- **`nexus/services/local_heal/local_model_executor.py`**:
  - Dynamically routes between topologies based on `signal_snapshot`.
  - Supports both `local_committee_only` (direct adapter-level scoring) and `localheal_pipeline` (delegated corrector loop).
- **`nexus/services/local_heal/local_committee_candidate_provider.py`**:
  - Loops over arbitrary lengths of `proposer_specs`.
  - Computes non-colliding `candidate_id`s by incorporating sequence indices and model slugs.
- **`nexus/services/local_heal/candidate_decision_adapter.py`**:
  - Filters out abstained/blocked candidates, runs Borda score aggregation, and ensures the selected candidate aligns to the Borda winner.
- **`nexus/services/local_heal/output_understanding.py`**:
  - Normalizes candidate outputs into parsed search-replace or unified-diff before sandboxed apply.

---

## 4. Bounded 10-Combination Execution Plan

To complete the full execution matrix validation, the following test matrix must be evaluated systematically on task `toy-math-verifier-evidence-gap` (or a similar lightweight validation task):

### 1. Dual Proposer Combinations (6 Groups)
- **A1**: Proposers: `qwen7b` + `deepseek67b`, Judge: `qwen3b`
- **A2**: Proposers: `qwen7b` + `ornith9b`, Judge: `qwen3b`
- **A3**: Proposers: `qwen7b` + `qwythos9b`, Judge: `qwen3b`
- **A4**: Proposers: `deepseek67b` + `ornith9b`, Judge: `qwen3b`
- **A5**: Proposers: `deepseek67b` + `qwythos9b`, Judge: `qwen3b`
- **A6**: Proposers: `ornith9b` + `qwythos9b`, Judge: `qwen3b`

### 2. Triple Proposer Combinations (4 Groups)
- **B1**: Proposers: `qwen7b` + `deepseek67b` + `ornith9b`, Judge: `qwen3b`
- **B2**: Proposers: `qwen7b` + `deepseek67b` + `qwythos9b`, Judge: `qwen3b`
- **B3**: Proposers: `qwen7b` + `ornith9b` + `qwythos9b`, Judge: `qwen3b`
- **B4**: Proposers: `deepseek67b` + `ornith9b` + `qwythos9b`, Judge: `qwen3b`

For each combination run, the runner must collect:
1. Candidate telemetry (counts, distinct model calls).
2. Unique candidate ID verification.
3. Winner mapping vs Borda score alignment.
4. Final verifier outcomes and exit codes.
5. Rejection classifications for failed candidates.
