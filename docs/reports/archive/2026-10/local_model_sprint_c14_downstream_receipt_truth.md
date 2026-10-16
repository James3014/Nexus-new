# LocalModel Sprint C14 Downstream Receipt Truth

**Status**: `LOCAL_MODEL_SPRINT_C14_DOWNSTREAM_RECEIPT_TRUTH_COMPLETE`

**Date**: 2026-06-30

**Commits**:
- `a325148ed` — wire LocalHeal downstream receipt truth
- `ccc95cc76` — fix LocalHeal no-block output classification (C13 carryover)

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | C14 receipt truth fields |
| `scripts/bench/m1_real_local_solve_benchmark.py` | C14 fields in JSONL |
| `docs/research/knowledge_agent_shadow_prep_receipt_truth.md` | Knowledge shadow prep |

## Tests Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  scripts/bench/m1_real_local_solve_benchmark.py

/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 49 passed

## Bounded M1 Result

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py
```

**Result**: Completed, 6 tasks, no timeout.

## toy-math-solve C14 Receipt Truth

| Field | Value | Meaning |
|-------|-------|---------|
| local_model_called | True | Executor shell reached |
| executor_shell_reached | True | Same as above |
| actual_model_called | True | Model was actually called |
| actual_provider_invoked | True | Provider was invoked |
| actual_model_output_len | 667 | Model produced 667 bytes |
| actual_model_name_used | qwen2.5-coder:7b-instruct | Correct model |
| no_patch_reason | search_mismatch | Why no patch was produced |
| output_class | UNKNOWN | C13 classification (model_decisions lost) |
| pipeline_failure_reason | SEARCH_MISMATCH:SEARCH_MISMATCH | Root cause |
| pipeline_final_patch_len | 0 | No patch produced |
| solved | false | Not claimed |

## 6-Task Table

| task_id | topology | executor_shell_reached | actual_model_called | actual_model_output_len | no_patch_reason | pipeline_final_patch_len | solved |
|---------|----------|----------------------|--------------------|-----------------------|----------------|------------------------|--------|
| astropy__astropy-13236 | local_committee_only | true | true | 0 | fenced_output | 0 | false |
| sympy__sympy-13852 | local_only | false | false | 0 | model_not_called | 0 | false |
| concurrency_bug_02 | local_only | false | false | 0 | model_not_called | 0 | false |
| toy-math-solve | localheal_pipeline | true | true | 667 | search_mismatch | 0 | false |
| task-a-real | local_committee_only | true | true | 0 | model_refusal | 0 | false |
| task-b-real | local_committee_only | true | true | 0 | model_refusal | 0 | false |

## Explicit Statements

- **No new route**: C14 only records downstream execution truth after route is chosen.
- **No new topology**: execution_topology comes from existing CapabilityPlanner decision.
- **No new selector**: No provider/model selection logic added.
- **No CapabilityPlanner change**: Route truth remains CapabilityPlanner + HybridRouteDecision.
- **No HybridRouteDecision change**: C14 reads existing decision, doesn't modify it.
- **No new provider call**: C14 doesn't trigger any provider invocation.
- **No solved claim**: All tasks show solved=false.

## Key Insight

C14 reveals the true execution state:

- `local_model_called=True` was misleading — it meant "executor shell reached" not "model produced useful output"
- New fields distinguish: `executor_shell_reached` vs `actual_model_called` vs `actual_model_output_len`
- `no_patch_reason` explains why no patch was produced (search_mismatch, no_blocks_found, model_refusal, etc.)

## Next Gate

- **Receipt truth is now clear**: We can see exactly where each task fails
- **If no_patch_reason=search_mismatch**: Source anchoring needs improvement
- **If no_patch_reason=no_blocks_found**: Protocol adherence needs improvement
- **If no_patch_reason=model_refusal**: Prompt or model selection needs improvement
- **If no_patch_reason=model_not_called**: Infrastructure/provider issue
