# T2.8 Execution Guard

## Branch Taken
T2.8 Attribution-Safe 20-Task Diagnostic

## T2.7 Status
Green (baseline manifest, evidence pack, 18 rules, export guard verified)

## Hard Stop Conditions
- IF receipt missing → stop, mark Red
- IF public_claim_allowed=true → stop, fix claim boundary
- IF model_calls=0 AND model_patch_reward > 0 → stop, fix attribution
- IF export_as_model_patch_success=true AND model_calls=0 → stop, fix export guard
- IF LLM-generated SEARCH directly applied → stop
- IF fuzzy threshold lowered → stop
- IF T2.7 anchor regresses → classify root cause

## Per-Task Telemetry Required
- instance_id, run_group=T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC
- simulated=false, claim_eligible=false, public_claim_allowed=false
- receipt_present, workspace_configured, dependency_check
- model_calls, solved, failure_class, verification_result
- canonical_span_source, recovery_rule_id
- model_patch_reward=0.0 (all tasks)
- export_as_model_patch_success=false (all tasks)

## Success Criteria
- 20/20 receipts present
- No public claim violation
- No attribution pollution
- All T2.7 anchors stable
- At least 70% solved or clean gate progression
