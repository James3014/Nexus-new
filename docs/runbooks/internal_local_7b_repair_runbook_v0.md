# Internal Local 7B Repair Runbook v0

## 1. Scope and Boundary

### Supported
- Internal local 7B repair workflow
- Real source checkout verification
- Baseline reproduction or blocker classification
- Local Ollama model execution (qwen2.5-coder:7b)
- Patch authority validation (VERBATIM / CANONICAL_RECOVERY / CROSS_FILE_CORRECTION)
- Task-scoped verification via MicroVerifier
- Receipt audit with claim separation
- S2T export classification
- Owner acceptance gate

### Not Supported
- Public benchmark claims
- Production readiness claims
- Training export
- Runtime/routing enablement
- Generalized repo-wide repair claims
- Automatic customer-facing repair
- 14B model validation (unless separately executed)

## 2. Entry Criteria

A task may enter the workflow when ALL are true:
- [ ] Task has source repo or source checkout can be created
- [ ] Expected base commit/tag is known or resolvable
- [ ] Verifier command is known or derivable
- [ ] Dependency setup is bounded
- [ ] No private credentials required
- [ ] No network-dependent verifier (unless explicitly approved)
- [ ] Task has expected lane hypothesis

## 3. Ten-Gate Procedure

### G0: Task Eligibility
- **Purpose**: Confirm task is valid and in scope
- **Inputs**: task_id, repo, target_file
- **Outputs**: eligibility_record.json
- **Pass**: All required fields present
- **Fail**: Missing required fields → reject
- **Blocker**: N/A
- **Artifact**: `eligibility_record.json`

### G1: Source Checkout
- **Purpose**: Verify source exists and is at correct version
- **Inputs**: source_path, expected_git_sha
- **Outputs**: source_checkout_record.json
- **Pass**: Source exists, git SHA matches
- **Fail**: Source missing or SHA mismatch
- **Blocker**: `V4C1_BLOCKED_BY_SOURCE_CHECKOUT`
- **Artifact**: `source_checkout_record.json`

### G2: Baseline Reproduction
- **Purpose**: Establish baseline or classify blocker
- **Inputs**: reproduction_command, interpreter
- **Outputs**: baseline_reproduction.json
- **Pass**: Reproduction succeeds OR blocker classified with env_taxonomy
- **Fail**: Reproduction fails AND cannot classify
- **Blocker**: `V4C1_BLOCKED_BY_REPRO_NOT_ESTABLISHED`
- **Artifact**: `baseline_reproduction.json`

### G3: Verifier Context
- **Purpose**: Ensure task-scoped verifier is available
- **Inputs**: env_taxonomy (interpreter, verifier_command)
- **Outputs**: verifier_context_record.json
- **Pass**: env_taxonomy has interpreter and verifier_command
- **Fail**: No task-scoped context available
- **Blocker**: `MICRO_VERIFY_CONTEXT_MISSING`
- **Artifact**: `verifier_context_record.json`

### G4: Model Execution
- **Purpose**: Run local model and record evidence
- **Inputs**: provider, model, prompt, source_context
- **Outputs**: model_execution.json
- **Pass**: model_calls > 0, cloud_api_used=false
- **Fail**: model_calls=0 or cloud_api_used=true
- **Blocker**: `V4C1_BLOCKED_BY_MODEL_EXECUTION`
- **Artifact**: `model_execution.json`

### G5: Patch Authority
- **Purpose**: Validate patch apply and authority attribution
- **Inputs**: patch_intent, source_text, localized_files
- **Outputs**: patch_authority_receipt.json
- **Pass**: apply_success=true, match_authority != None
- **Fail**: apply fails OR match_authority=None on success
- **Blocker**: `V4C1_BLOCKED_BY_ATTRIBUTION_REGRESSION`
- **Artifact**: `patch_authority_receipt.json`

### G6: Verification
- **Purpose**: Run task-scoped verifier
- **Inputs**: verifier_command, interpreter, patched_files
- **Outputs**: final_verification.json
- **Pass**: verifier_status=passed OR env-blocked with classification
- **Fail**: verifier_status=failed
- **Blocker**: `VERIFIER_FAILED_PATCH`
- **Artifact**: `final_verification.json`

### G7: Export Classification
- **Purpose**: Classify via S2TExportGuard
- **Inputs**: match_authority, model_calls, deterministic_fallback_used
- **Outputs**: export_classification.json
- **Pass**: classification assigned, public_claim=false, training=false
- **Fail**: public_claim=true OR training=true
- **Blocker**: `GOVERNANCE_REGRESSION`
- **Artifact**: `export_classification.json`

### G8: Claim/Export Governance
- **Purpose**: Final governance check
- **Inputs**: all prior gate outputs
- **Outputs**: governance_check.json
- **Pass**: All governance fields correct
- **Fail**: Any governance field incorrect
- **Blocker**: `GOVERNANCE_REGRESSION`
- **Artifact**: `governance_check.json`

### G9: Owner Acceptance
- **Purpose**: Human review and approval
- **Inputs**: all prior gate outputs, real_replay_result.json
- **Outputs**: owner_acceptance.json
- **Pass**: Owner approves with documented rationale
- **Fail**: Owner rejects
- **Blocker**: `PENDING_OWNER_REVIEW`
- **Artifact**: `owner_acceptance.json`

## 4. Receipt Schema

```json
{
  "task_id": "string",
  "repo": "string",
  "source_git_sha": "string",
  "execution_mode": "real",
  "provider": "ollama",
  "model": "qwen2.5-coder:7b",
  "model_calls": 1,
  "cloud_api_used": false,
  "deterministic_fallback_used": false,
  "match_authority": "verbatim|canonical_recovery|cross_file_correction|null",
  "success_attribution": "model_patch_success|canonical_recovery_success|cross_file_recovery_success|null",
  "export_classification": "model_patch_success_candidate|canonical_recovery_success|tool_demonstration|human_review_required|internal_infra_failure|verification_failure",
  "task_scoped": true,
  "verifier_status": "passed|failed|not_run|env_blocked",
  "blocker_type": "string|null",
  "public_claim_allowed": false,
  "training_eligible": false,
  "final_lane": "verifier_passed_by_execution|canonical_recovery_success|env_blocked_but_review_verified",
  "final_status": "string"
}
```

## 5. Lane Classification Guide

### Direct Model Patch Success
- match_authority: VERBATIM
- success_attribution: model_patch_success
- export_classification: model_patch_success_candidate
- final_lane: verifier_passed_by_execution

### Canonical Recovery Success
- match_authority: CANONICAL_RECOVERY
- success_attribution: canonical_recovery_success
- export_classification: canonical_recovery_success
- final_lane: canonical_recovery_success

### Cross-File Recovery Success
- match_authority: CROSS_FILE_CORRECTION
- success_attribution: cross_file_recovery_success
- export_classification: canonical_recovery_success
- final_lane: canonical_recovery_success

### Env-Sensitive Blocker
- match_authority: null
- success_attribution: null
- export_classification: human_review_required OR internal_infra_failure
- final_lane: env_blocked_but_review_verified

### Non-Collapse Rules
- Canonical recovery is NOT direct model success
- Env-blocked is NOT model success
- Env-blocked is NOT model failure (unless verifier evidence supports it)
- Code-review parity is NOT verifier-backed execution success

## 6. Stop Rules

| Rule | Trigger | Action |
|------|---------|--------|
| SR-1 | match_authority=None on success | STOP |
| SR-2 | FUZZY_CANDIDATE_ONLY success | STOP |
| SR-3 | Generic python3 silent fallback | STOP |
| SR-4 | model_calls=0 with model success claimed | STOP |
| SR-5 | cloud_api_used=true | STOP |
| SR-6 | Deterministic fallback counted as model success | STOP |
| SR-7 | public_claim_allowed=true | STOP |
| SR-8 | training_eligible=true | STOP |
| SR-9 | Runtime/routing integration enabled | STOP |
| SR-10 | Source checkout missing | STOP |
| SR-11 | Reproduction cannot be classified | STOP |

## 7. Artifact Layout

```
artifacts/runtime/<task_id>/
├── environment_preflight.json
├── baseline_reproduction.json
├── model_execution.json
├── patch_authority_receipt.json
├── final_verification.json
├── real_replay_result.json
├── receipt_audit.md
└── final_report.md
```

## 8. Owner Review Checklist

- [ ] Source proof: source_checkout_record.json exists
- [ ] Model proof: model_execution.json, model_calls > 0
- [ ] Verifier proof: final_verification.json, task_scoped=true
- [ ] Attribution proof: patch_authority_receipt.json, match_authority != None
- [ ] Classification proof: export_classification.json
- [ ] Governance proof: public_claim=false, training=false
- [ ] Residual caveats documented

## 9. Final Status Taxonomy

| Status | Meaning |
|--------|---------|
| INTERNAL_REPAIR_PASS_INTERNAL_ONLY | Repair succeeded with all gates passed |
| INTERNAL_REPAIR_PASS_WITH_CAVEATS | Repair succeeded with documented caveats |
| BLOCKED_BY_SOURCE_CHECKOUT | Source unavailable |
| BLOCKED_BY_DEPENDENCY_SETUP | Dependencies cannot be installed |
| BLOCKED_BY_REPRO_NOT_ESTABLISHED | Reproduction not established |
| BLOCKED_BY_MICRO_VERIFY_CONTEXT | No task-scoped verifier context |
| VERIFIER_FAILED_PATCH | Verifier rejected patch |
| BLOCKED_BY_ATTRIBUTION_REGRESSION | match_authority=None on success |
| BLOCKED_BY_CLAIM_COLLAPSE | Canonical recovery collapsed into model success |
| GOVERNANCE_REGRESSION | public_claim or training flag incorrect |
| HUMAN_REVIEW_REQUIRED | Requires human review |
| INTERNAL_INFRA_FAILURE | Infrastructure failure |

## 10. Example Traces

### MC001 Direct Patch Lane
```
G0: PASS (astropy-13236, table.py)
G1: PASS (95df21d, v5.2.1)
G2: PASS (reproduced)
G3: PASS (env_taxonomy.astropy)
G4: PASS (model_calls=1, cloud=false)
G5: PASS (match_authority=verbatim)
G6: PASS (verifier=passed)
G7: PASS (classification=model_patch_success_candidate)
G8: PASS (public=false, training=false)
G9: PASS (owner approved)
Status: INTERNAL_REPAIR_PASS_INTERNAL_ONLY
```

### MC006 Canonical Recovery Lane
```
G0: PASS (sympy-13852, zeta_functions.py)
G1: PASS (8059df7, sympy-1.12)
G2: PASS (reproduced)
G3: PASS (env_taxonomy.sympy)
G4: PASS (model_calls=1, cloud=false)
G5: PASS (match_authority=canonical_recovery)
G6: PASS (verifier=passed)
G7: PASS (classification=canonical_recovery_success)
G8: PASS (public=false, training=false)
G9: PASS (owner approved)
Status: INTERNAL_REPAIR_PASS_INTERNAL_ONLY
```

### MC008 Env-Sensitive Lane
```
G0: PASS (astropy-14182, rst.py)
G1: PASS (95df21d, v5.2.1)
G2: BLOCKED (DEPENDENCY_SETUP_MISSING → human_review_required)
G3: PASS (env_taxonomy.astropy)
G4: SKIPPED (blocked at G2)
G5: SKIPPED (blocked at G2)
G6: SKIPPED (blocked at G2)
G7: PASS (classification=human_review_required)
G8: PASS (public=false, training=false)
G9: PASS (owner approved)
Status: HUMAN_REVIEW_REQUIRED
```
