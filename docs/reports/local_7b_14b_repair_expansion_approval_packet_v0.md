# Local 7B/14B Repair Expansion Approval Packet v0

**Status**: READY_FOR_OWNER_DECISION  
**Generated**: 2026-06-20  
**Source hardening commit**: 85d3e1f0b140c0014e59e3bd4b2643da701fe614  

## Summary

All pre-expansion hardening gates passed. This packet defines the next 6-task expansion batch for owner approval. No repair execution, model calls, or verifier runs were performed in this task.

## Candidate Tasks (6)

| Task ID | Category | Evidence Tier | Flakiness | Retry Budget | Abstention |
|---------|----------|---------------|-----------|--------------|------------|
| astropy_14526 | deterministic_patch_task | subprocess_pytest_nexus_venv_verified | low | 2 | yes |
| sympy_polys_01 | deterministic_patch_task | retry_aware_subprocess_python_task_venv_verified | low | 2 | yes |
| nexus_verifier_http_01 | env_lane_task | subprocess_pytest_nexus_venv_verified | medium | 3 | yes |
| nexus_protocol_boundary_01 | transport_authority_task | subprocess_pytest_nexus_venv_verified | low | 2 | no |
| concurrency_bug_03 | concurrency_repeatability_task | stress_test_verified | high | 3 | yes |
| sympy_matrices_abstention_candidate | abstention_candidate | abstention_correct | low | 1 | yes |

## Guardrails

- Task-scoped interpreter required (no bare python3)
- MicroVerifier: pre-verifier only
- FUZZY_CANDIDATE_ONLY: fail-closed
- CANONICAL_RECOVERY: attribution-separated
- StructuredPacket must feed retry prompt
- No runtime/routing integration
- No training export / public claim / automatic adoption

## Owner Decision Required

```
owner_decision: owner_decision_required
default_decision: REJECT_AND_KEEP_ARCHIVED
```

## Artifacts

- `approval_packet_summary.json`
- `candidate_task_approval_list.jsonl` (6 candidates)
- `model_role_policy.json`
- `expansion_guardrails.json`
- `verifier_and_evidence_policy.json`
