# P4-I1 Committee Routed-Tool Contract Report

## Status: ✅ COMPLETE (committed: `d899ff802`)

## Files Changed (3)

| File | Action |
|------|--------|
| `nexus/services/local_heal/committee_routed_tool.py` | +73 — Request/Result dataclasses + validator + receipt builder |
| `nexus/services/local_heal/receipt.py` | +14 — 13 new P4 receipt fields |
| `tests/unit/local_heal/test_p4_committee_routed_tool_contract.py` | +155 — 10 tests |

## Contract Schema

**Request**: `task_id`, `repo_root`, `target_file`, `target_symbol`, `locked_search`, `source_hash`, `difficulty`, `p3_route_status`, `hard_case_escalation_reason`, `evidence_refs`, `proposer_specs`, `judge_model`, `max_candidates`, `mutation_allowed`, `verifier_allowed`

**Result**: `invoked`, `invocation_allowed`, `blocked_reason`, `candidate_count`, `canonical_candidate_count`, `selected_candidate_hash`, `selected_candidate_source_model`, `selected_candidate_apply_status`, `selected_candidate_verifier_status`, `winner_found`, `solved_by_committee`, `failure_reasons`, `receipt_fragment`

## Fail-closed Conditions

- missing `target_file` → blocked
- `proposer_specs < 2` → blocked
- missing `judge_model` → blocked
- missing `task_id` → blocked

## Receipt Fields Added (13)

`p4_committee_invoked`, `p4_committee_invocation_allowed`, `p4_committee_blocked_reason`, `p4_committee_candidate_count`, `p4_canonical_candidate_count`, `p4_selected_candidate_hash`, `p4_selected_candidate_model`, `p4_selected_candidate_apply_status`, `p4_selected_candidate_verifier_status`, `p4_winner_found`, `p4_solved_by_committee`, `p4_failure_reasons`, `p4_fail_closed`

## Test Results

```
P4-I1:     10 passed
P3 regress: 50 passed
Full suite: 1366 passed, 1 skipped, 0 failed
```

## Next

✅ P4-I1 complete → ready for **P4-I2: Activation / Suppression Gate**
