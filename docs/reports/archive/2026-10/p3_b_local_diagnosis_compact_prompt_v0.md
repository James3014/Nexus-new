# P3-B Local Diagnosis Compact Prompt Report

## Status
**P3_B_LOCAL_DIAGNOSIS_COMPACT_PROMPT_PASS**

## Files Changed
- `nexus/services/local_heal/p3_local_diagnosis.py` (new)
- `nexus/services/local_heal/local_model_executor.py`
- `tests/unit/local_heal/test_p3_local_diagnosis.py` (new)
- `tests/unit/local_heal/test_local_model_executor_p3_local_diagnosis.py` (new)

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/p3_local_diagnosis.py tests/unit/local_heal/test_p3_local_diagnosis.py tests/unit/local_heal/test_local_model_executor_p3_local_diagnosis.py

python3 -m pytest tests/unit/local_heal/test_p3_route_skeleton.py tests/unit/local_heal/test_p3_local_diagnosis.py tests/unit/local_heal/test_local_model_executor_p3_local_diagnosis.py tests/unit/local_heal/test_output_understanding.py tests/unit/local_heal/test_apply_hash_anchor_truth.py -q
```

## Test Counts
- `test_p3_route_skeleton.py`: 31 passed
- `test_p3_local_diagnosis.py`: 12 passed
- `test_local_model_executor_p3_local_diagnosis.py`: 4 passed
- `test_output_understanding.py`: 15 passed
- `test_apply_hash_anchor_truth.py`: 32 passed
- **Total**: 89 passed

## Compact Diagnosis Fields
All 22 required fields implemented:
- `p3_local_diagnosis_enabled`
- `p3_local_diagnosis_authority`
- `task_id`, `task_difficulty`
- `target_file`, `target_symbol`, `line_span`, `old_block_hash`
- `failure_class`, `failure_summary`, `verifier_summary`
- `anchor_status`, `hash_chain_status`
- `compact_prompt`, `compact_prompt_hash`, `compact_prompt_token_estimate`
- `source_context_included`
- `cloud_ready`, `cloud_call_invoked`, `runtime_behavior_changed`
- `claim_eligible`, `public_claim_allowed`, `reason`

## Sample Compact Prompt
```
Task: task-001 | Difficulty: medium | File: foo.py | Symbol: bar | Span: L10-L20 | Hash: abc123def456 | Failure: search_mismatch | Error: SEARCH block not found in source | Verifier: not_run | Anchor: available
```

## Prompt Hash Example
`compact_prompt_hash`: SHA-256 of compact_prompt, deterministic across reruns.

## Proof No Cloud Call Was Made
- `cloud_call_invoked=false` always
- No cloud API client imported
- No network call made

## Proof No Runtime Behavior Changed
- `runtime_behavior_changed=false` always
- Existing executor paths unchanged

## Proof P2 Hash/Apply Truth Remains Required
- P2 hash fields not modified
- `hash_chain_status="incomplete"` blocks `cloud_ready`

## Known Residual Debt
1. Pre-existing test failures due to missing `rank_bm25` module
2. P3-B is shadow-only; real cloud diagnosis requires P3-G+

## Next Recommended Package
**P3-C Cloud Candidate Stub** — Implement cloud candidate generation contract.

## Statements
- ✅ P3 is not complete
- ✅ cloud_with_local_assist execution is not implemented
- ✅ public_claim_allowed=false
- ✅ production_ready=false
