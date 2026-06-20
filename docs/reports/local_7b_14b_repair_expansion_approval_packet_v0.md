# Local 7B/14B Repair Expansion Approval Packet v0

**Status**: READY_FOR_OWNER_DECISION (COMPLETE)  
**Generated**: 2026-06-20  
**Source hardening commit**: 85d3e1f0b140c0014e59e3bd4b2643da701fe614  
**Initial packet commit**: f7f4b043  

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

## Abort Conditions (17)

| ID | Condition |
|----|----------|
| AC-01 | Unapproved file mutation |
| AC-02 | Sealed artifact mutation |
| AC-03 | Runtime integration attempted |
| AC-04 | Routing integration attempted |
| AC-05 | Verifier override attempted |
| AC-06 | Training export attempted |
| AC-07 | Public claim appears |
| AC-08 | GPT/Gemini parity claim |
| AC-09 | Production-ready claim |
| AC-10 | Model claims success without verifier pass |
| AC-11 | FUZZY_CANDIDATE_ONLY becomes apply authority |
| AC-12 | Canonical recovery misattributed as model success |
| AC-13 | Retry record missing required fields |
| AC-14 | Wrong interpreter or env |
| AC-15 | Concurrency task timing hack |
| AC-16 | Test weakening |
| AC-17 | Abstention candidate forced into patch |

## Owner Decision Options

| Decision | Tasks | Risk |
|---------|-------|------|
| APPROVE_6_TASKS | all 6 | medium_high |
| APPROVE_4_TASKS | deterministic + env + protocol | medium |
| APPROVE_DETERMINISTIC_ONLY | astropy_14526 + sympy_polys_01 | low |
| APPROVE_WITHOUT_CONCURRENCY | 5 tasks, no concurrency_bug_03 | medium |
| REQUEST_SMALLER_SCOPE | none | none |
| REQUEST_MORE_HARDENING | none | none |
| **REJECT_AND_KEEP_ARCHIVED** (DEFAULT) | none | none |

## Future Execution Output Schema

Required output files (16): selected_task_batch.jsonl, model_call_receipts.jsonl, task_execution_records.jsonl, advisory_records.jsonl, localization_records.jsonl, patch_plan_records.jsonl, patch_generation_records.jsonl, patch_validation_results.jsonl, verifier_results.jsonl, retry_records.jsonl, abstention_records.jsonl, repair_receipts.jsonl, execution_summary.json, governance_summary.json, failure_analysis_seed.json, docs report.

Required row fields: task_id, model, attempt_index, retry_count, evidence_citation, verifier_command, interpreter_or_venv, evidence_tier, final_status, match_authority, training_export_allowed, public_claim_allowed, automatic_adoption.

## Governance Summary

- model_calls_executed: false
- repair_execution_authorized: false
- runtime_integration: false
- routing_integration: false
- training_export_allowed: false
- public_claim_allowed: false
- automatic_adoption: false
- owner_decision_required: true

## Packet Completion Status

| Part | File | Status |
|------|------|--------|
| A | approval_packet_summary.json | COMPLETE |
| B | candidate_task_approval_list.jsonl | COMPLETE |
| C | model_role_policy.json | COMPLETE |
| D | expansion_guardrails.json | COMPLETE |
| E | verifier_and_evidence_policy.json | COMPLETE |
| F | abort_conditions.json | COMPLETE |
| G | owner_decision_options.json | COMPLETE |
| H | future_execution_output_schema.json | COMPLETE |
| I | governance_summary.json | COMPLETE |

**owner_decision: owner_decision_required**  
**default_decision: REJECT_AND_KEEP_ARCHIVED**
