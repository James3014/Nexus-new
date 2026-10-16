# V4-C Operations Readiness Plan

## Status: V4C_OPERATIONS_READINESS_PLAN_READY

## 1. Capability Boundary

### Supported Internally
- Local 7B repair evidence handling
- Direct patch lane (VERBATIM authority)
- Canonical recovery lane (CANONICAL_RECOVERY authority)
- Env-sensitive blocker lane (human_review_required classification)
- Verifier-backed receipt with claim separation
- Internal-only capability statement

### Not Yet Supported
- Public benchmark claim
- Production readiness
- Automatic runtime/routing
- Training export
- Generalized cross-repo repair claim
- 14B validation (unless separately executed)

## 2. Internal Workflow

```
Task Intake → Source Checkout → Env Taxonomy → Baseline Reproduction
    ↓
Local Model Execution → Patch Authority Validation → Task-Scoped Verification
    ↓
S2T Export Classification → Claim Separation → Owner Acceptance → Final Classification
```

### Steps
1. **Task Intake**: Accept task with instance_id, repo, target_file
2. **Source Checkout**: Verify source exists at bounded path
3. **Env Taxonomy**: Classify environment requirements
4. **Baseline Reproduction**: Run baseline or classify blocker
5. **Local Model Execution**: Run Ollama qwen2.5-coder:7b, record model_calls
6. **Patch Authority Validation**: Apply patch, verify match_authority non-null
7. **Task-Scoped Verification**: Run MicroVerifier with env_taxonomy context
8. **S2T Export Classification**: Classify via S2TExportGuard
9. **Claim Separation**: Verify public_claim_allowed=false, training_eligible=false
10. **Owner Acceptance**: Human review and approval

## 3. Gate Design

| Gate | Name | Check | Fail Action |
|------|------|-------|-------------|
| G0 | Task Eligibility | task_id, repo, target_file provided | Reject |
| G1 | Source Checkout | source path exists, git SHA recorded | BLOCKED_BY_SOURCE |
| G2 | Baseline Reproduction | reproduced OR blocker classified | BLOCKED_BY_REPRO |
| G3 | Verifier Context | env_taxonomy has interpreter/verifier_command | MICRO_VERIFY_CONTEXT_MISSING |
| G4 | Model Execution | model_calls > 0, cloud_api_used=false | BLOCKED_BY_MODEL |
| G5 | Patch Authority | match_authority != None on success | ATTRIBUTION_REGRESSION |
| G6 | Verifier Result | verifier pass/fail recorded | VERIFIER_FAILED |
| G7 | Claim/Export Governance | public_claim=false, training=false | GOVERNANCE_REGRESSION |
| G8 | Owner Acceptance | Human review approved | PENDING_OWNER |

## 4. Receipt Schema

```json
{
  "task_id": "string",
  "repo": "string",
  "source_git_sha": "string",
  "execution_mode": "real",
  "provider": "ollama",
  "model": "qwen2.5-coder:7b",
  "model_calls": "integer",
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

## 5. Stop Rules

| Rule | Trigger | Action |
|------|---------|--------|
| SR-1 | match_authority=None on success | STOP: attribution regression |
| SR-2 | FUZZY_CANDIDATE_ONLY success | STOP: invariant violation |
| SR-3 | Generic python3 silent fallback | STOP: context missing |
| SR-4 | Env-blocked counted as model success | STOP: claim collapse |
| SR-5 | Canonical recovery collapsed into model success | STOP: claim collapse |
| SR-6 | public_claim_allowed=true | STOP: governance regression |
| SR-7 | training_eligible=true | STOP: governance regression |
| SR-8 | Runtime/routing enablement | STOP: scope violation |

## 6. Recommendation

**V4C_READY_FOR_INTERNAL_REPAIR_RUNBOOK**

All gates defined. Receipt schema stabilized. Stop rules documented. Ready to convert into internal runbook for repeatable repair execution.
