# Receipt Fields

## LocalModelExecutor Summary Fields

| Field | Where Produced | Where Consumed | Test | Default Safe Value |
|-------|---------------|----------------|------|-------------------|
| `local_executor_planned` | CapabilityPlanner | Receipt | test_local_model_executor.py | false |
| `local_executor_selected_by` | CapabilityPlanner | Receipt | test_local_model_executor.py | "" |
| `local_model_called` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | false |
| `candidate_hash` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | "" |
| `selected_candidate_hash` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | "" |
| `applied_patch_hash` | run_isolated_workspace_apply | Receipt | test_isolated_workspace_apply.py | "" |
| `selected_candidate_hash_matches_applied` | run_isolated_workspace_apply | Receipt | test_isolated_workspace_apply.py | false |
| `candidate_output_isolated` | run_isolated_workspace_apply | Receipt | test_isolated_workspace_apply.py | false |
| `verifier_result` | run_isolated_verifier | Receipt | test_isolated_verifier.py | "not_run" |
| `local_executor_receipt` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | {} |
| `capability_receipts` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | {} |
| `local_model_executor_summary` | LocalModelExecutor._run_impl | Receipt | test_local_model_executor.py | {} |
| `public_claim_allowed` | All receipts | Receipt | test_candidate_isolation_gate.py | false |
| `production_ready` | All receipts | Receipt | test_candidate_isolation_gate.py | false |
| `behavior_changed` | CapabilityPlanner | Receipt | test_capability_planner.py | false |
| `route_truth_violation_count` | CapabilityPlanner | Receipt | test_capability_planner.py | 0 |
| `localheal_pipeline_invoked` | LocalHealPipelineCapabilityExecutor | Receipt | test_localheal_pipeline_seam_truth.py | false |
| `localheal_pipeline_run_called` | LocalHealPipelineCapabilityExecutor | Receipt | test_localheal_pipeline_seam_truth.py | false |
| `localheal_pipeline_actual_execution` | LocalHealPipelineCapabilityExecutor | Receipt | test_localheal_pipeline_seam_truth.py | false |
| `localheal_pipeline_availability_only` | LocalHealPipelineCapabilityExecutor | Receipt | test_localheal_pipeline_seam_truth.py | true |
| `diagnosis_committee_invoked` | CommitteeOrchestrator | Receipt | test_c6aw_da_committee_runtime_activation.py | false |
| `audit_committee_invoked` | CommitteeOrchestrator | Receipt | test_c6aw_da_committee_runtime_activation.py | false |

## CandidateIsolationReceipt Fields

| Field | Default Safe Value |
|-------|-------------------|
| `candidate_id` | "" |
| `selected_candidate_hash` | "" |
| `applied_patch_hash` | "" |
| `selected_candidate_hash_matches_applied` | false |
| `candidate_output_isolated` | false |
| `verifier_result` | "not_run" |
| `public_claim_allowed` | false |
| `production_ready` | false |
| `repaired_by_rule` | "none" |
| `candidate_target_file` | "" |
| `candidate_target_symbol` | "" |

## IsolatedApplyReceipt Fields

| Field | Default Safe Value |
|-------|-------------------|
| `patch_apply_status` | "blocked" |
| `applied_patch_hash` | "" |
| `selected_candidate_hash_matches_applied` | false |
| `public_claim_allowed` | false |
| `production_ready` | false |

## IsolatedVerifierReceipt Fields

| Field | Default Safe Value |
|-------|-------------------|
| `verifier_status` | "not_run" |
| `public_claim_allowed` | false |
| `production_ready` | false |
