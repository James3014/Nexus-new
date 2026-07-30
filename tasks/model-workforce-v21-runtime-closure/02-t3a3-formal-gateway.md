# T3A3 - Formal Gateway Workforce Admission

**task_id:** `model-workforce-v21-runtime-closure-t3a3`
**artifact_authority:** current
**owner:** James Chen
**status:** CANDIDATE_READY
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

Connect Gateway `ask_unified` physical Online invocation to the existing `CapabilityPlanner` workforce admission and gateway invocation authority:

`BattlesuitGateway.ask_unified -> MainchainEntry -> CapabilityPlanner -> UnifiedRuntime -> registered Online transport`

The implementation must reuse the existing planner, `MainchainEntry`, `UnifiedRuntime`, Gateway `ask_unified`, and existing gateway authority validation. It must not create a new route, topology selector, policy authority, model authority, or provider fallback.

## Authority and inputs

- Campaign index: `tasks/model-workforce-v21-runtime-closure/INDEX.md`
- Workforce policy authority: `docs/arch/MODEL_WORKFORCE_POLICY.md`
- Machine workforce source: `nexus/config/model_workforce.yaml`
- User activation: in-session request for approved T3A3 execution after integrated T3B2B in the isolated Target

## Dependencies

- T3B2B candidate integrated at `540ad189d704e5d2d5242c3326fb744df16bcb8c`.
- Branch/Target: `nexus/task/model-workforce-v21-runtime-closure-t3a3`.

## Allowed files

- `nexus/services/gateway.py`
- `tests/services/test_unified_runtime.py`
- `tests/services/test_unified_runtime_workforce_admission.py`
- `tests/services/test_formal_mainchain_callers.py`
- `tasks/model-workforce-v21-runtime-closure/INDEX.md`
- `tasks/model-workforce-v21-runtime-closure/02-t3a3-formal-gateway.md`

## Forbidden scope

- Do not edit runtime routing/topology authority outside the allowed files.
- Do not create new reports, ADRs, plans, benchmark artifacts, lifecycle JSON, or wiki pages.
- Do not stage, commit, reset, delete, merge, push, approve, integrate, or clean up outside this card's allowed scope.
- Do not create provider fallback, route fallback, topology selector, model policy authority, or public-claim authority.

## Verification commands

```text
uv run pytest -q tests/services/test_unified_runtime.py tests/services/test_unified_runtime_workforce_admission.py tests/services/test_formal_mainchain_callers.py
git diff --check
```

## Evidence required

- Positive bounded Gateway `ask_unified` receipt proving admitted Online workforce binding is propagated into route provider, transport provider, invoker provider, online model, gateway invocation authority, and registered physical transport invocation.
- Negative zero-call denial for missing binding, malformed transport authority, provider mismatch, invoker-provider mismatch, and model mismatch.
- Receipt lineage preserving admission policy hash, binding hash, aggregate binding hash, planner decision id, gateway invocation authority, process evidence, and context trace surfaces.
- Exact verifier command output.
- Scoped commit SHA.

## Exit criteria

This card may claim only `T3A3_FORMAL_GATEWAY_WORKFORCE_ADMISSION_CANDIDATE_READY` after all verification commands pass, allowed-file scope is confirmed, deletion checks are clean, and a scoped implementation commit is formed.

It must not claim benchmark value, public claim eligibility, integration, downstream task activation, or production readiness.

## Residual debt and block classification

- `RECOVERABLE_BLOCK`: temporary environment, dependency, or sandbox failure that prevents verifier execution while code state can be preserved.
- `HARD_BLOCK`: authority conflict, unsafe route/topology change requirement, inability to keep edits within allowed files, or inability to form a scoped commit safely.
- Any block prevents Candidate promotion, integration, cleanup, public claims, and successor activation.
