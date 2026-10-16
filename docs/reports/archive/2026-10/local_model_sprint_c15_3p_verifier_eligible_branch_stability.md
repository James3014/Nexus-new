# C15-3P Verifier-Eligible Branch Stability and Delegated Retry Outcome Matrix

## Status
`LOCAL_MODEL_SPRINT_C15_3P_BRANCH_STABILITY_PASS`

## Execution Summary
- **Exact Commands Run**:
  - Deterministic checks:
    ```bash
    python3 -m py_compile \
      nexus/services/local_heal/local_model_executor.py \
      nexus/services/local_heal/orchestrator.py \
      scripts/bench/m1_real_local_solve_benchmark.py \
      tests/unit/local_heal/test_local_model_executor.py \
      tests/benchmark/test_m1_real_local_solve_benchmark.py
    ```
    ```bash
    uv run pytest \
      tests/unit/local_heal/test_local_model_executor.py \
      tests/benchmark/test_m1_real_local_solve_benchmark.py \
      -q
    ```
  - Live attempts execution command:
    ```bash
    export NEXUS_BENCHMARK_APPEND=1
    timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
    ```
- **Deterministic Test Count**: 148 passed
- **Number of Live Attempts**: 3
- **Reason for Early Stop**: Attempt 3 reached `pipeline_retry_delegated=true` and `delegated_retry_failure_reason="EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE"` (non-empty).

## Live Attempts Table
| Attempt Index | Task ID | Topology | Reanchored | Reached Delegated Retry | Delegated Retry Outcome | Branch Classification |
|---|---|---|---|---|---|---|
| 1 | toy-math-solve | localheal_pipeline | false | false | N/A | `patch_apply_failed_search_block_mismatch` |
| 2 | toy-math-solve | localheal_pipeline | false | false | N/A | `patch_apply_failed_search_block_mismatch` |
| 3 | toy-math-solve | localheal_pipeline | true | true | `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE` | `delegated_retry_empty_response` |

## Metrics & Branch Counts
- **Total Attempts**: 3
- **Count by Classification**:
  - `patch_apply_failed_search_block_mismatch`: 2
  - `delegated_retry_empty_response`: 1
- **Verifier-Eligible Branch Reached**: Yes (Attempt 3)
- **Pipeline Retry Delegated Reached**: Yes (Attempt 3)
- **Delegated Retry Output Empty**: Yes (`MODEL_EMPTY_RESPONSE`)
- **Shared-Client Live Outcome Proven/Pending**: Proven (Attempt 3 successfully went through the shared client call flow, confirming that Ollama model server responded with EMPTY_RESPONSE. The client wiring is functionally active.)
- **Reanchor Used Live**: Yes (Attempt 3)

## Decision Gate
- **Selected Decision Gate**: `B` (any attempt is `delegated_retry_empty_response`)
- **Next Recommended Phase**: `C15-3Q Delegated Retry Empty Response Root Cause`

## Source Fix Actions
- **Files Modified**: [m1_real_local_solve_benchmark.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/m1_real_local_solve_benchmark.py)
- **Rationale**: Added missing row projection mapping for `attempt_index`, `protocol_normalization`, and `delegated_retry_*` fields from `adapter_meta` to the output results JSONL row, matching the `missing row projection for existing fields` category. Enabled safe appending of results when `NEXUS_BENCHMARK_APPEND=1` environment variable is set.

## Enforcement Boundaries & Boundary Declarations
- route changed: no
- topology changed: no
- retry loop added: no
- CapabilityPlanner changed: no
- HybridRouteDecision changed: no
- prompt changed: no
- parser changed: no
- verifier behavior changed: no
- candidate isolation behavior changed: no
- full benchmark: no
- bounded toy live attempts only: yes (3 attempts)
- not toy-math-solve solved unless verifier passed: yes (solved=false since verifier failed/empty response)
- not local model armor ready: yes (armor ready=false)
- production_ready=false
- public_claim_allowed=false
