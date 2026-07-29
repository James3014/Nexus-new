# T3B2B - Formal Local Executor Runtime Seam

**task_id:** `model-workforce-v21-runtime-closure-t3b2b`
**artifact_authority:** current
**owner:** James Chen
**status:** IN_PROGRESS
**read_only:** false
**audit_only:** false
**commit_forbidden:** false
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Connect CapabilityPlanner workforce admission to the existing formal local executor runtime seam:

`UnifiedRuntime._run_local -> LocalAssistService.handle -> LocalModelExecutor.run`

The implementation must reuse the existing planner, `WorkforcePolicyLoader`, runtime admission authority, `LocalAssistService`, and `LocalModelExecutor`. It must not create a new route, topology selector, provider fallback, or model workforce authority.

## Authority and inputs

- Campaign index: `tasks/model-workforce-v21-runtime-closure/INDEX.md`
- Workforce policy authority: `docs/arch/MODEL_WORKFORCE_POLICY.md`
- Machine workforce source: `nexus/config/model_workforce.yaml`
- User activation: in-session request for approved T3B2B execution in the isolated Target

## Dependencies

- G0 governance bootstrap integrated.
- Branch/Target: `nexus/task/model-workforce-v21-runtime-closure-t3b2b`.

## Allowed files

- `nexus/services/unified_runtime.py`
- `nexus/services/local_assist_service.py`
- `nexus/services/local_heal/local_model_executor.py`
- `tests/services/test_unified_runtime_workforce_admission.py`
- `tests/services/test_unified_runtime.py`
- `tests/services/test_local_assist_service.py`
- `tasks/model-workforce-v21-runtime-closure/INDEX.md`
- `tasks/model-workforce-v21-runtime-closure/01-t3b2b-formal-local-executor.md`

## Forbidden scope

- Do not edit runtime routing/topology authority outside the allowed files.
- Do not create new reports, ADRs, plans, benchmark artifacts, lifecycle JSON, or wiki pages.
- Do not stage, commit, reset, delete, merge, push, approve, integrate, or clean up outside this card's allowed scope.
- Do not treat local model output as promotion, production readiness, public-claim evidence, or verifier truth.

## Verification commands

```text
uv run pytest -q tests/services/test_unified_runtime_workforce_admission.py tests/services/test_unified_runtime.py tests/services/test_local_assist_service.py
git diff --check
```

## Evidence required

- Positive bounded local invocation receipt showing runtime admission authority, `LocalAssistService` response schema, `LocalModelExecutor.run` physical callable, candidate isolation, verifier pass surface, and lineage on local/context receipt surfaces.
- Negative zero-call denial for malformed/adulterated authority and provider/model/task mismatches.
- Receipt lineage preserving admission policy hash, binding hash, aggregate binding hash, planner decision id, local authority, and formal local runtime lineage.
- Exact verifier command output.
- Scoped commit SHA.

## Exit criteria

This card may claim only `T3B2B_FORMAL_LOCAL_RUNTIME_WIRING_CANDIDATE_READY` after all verification commands pass, allowed-file scope is confirmed, deletion checks are clean, and a scoped implementation commit is formed.

It must not claim benchmark value, public claim eligibility, integration, downstream task activation, or production readiness.

## Residual debt and block classification

- `RECOVERABLE_BLOCK`: temporary environment, dependency, or sandbox failure that prevents verifier execution while code state can be preserved.
- `HARD_BLOCK`: authority conflict, unsafe route/topology change requirement, inability to keep edits within allowed files, or inability to form a scoped commit safely.
- Any block prevents Candidate promotion, integration, cleanup, public claims, and successor activation.
