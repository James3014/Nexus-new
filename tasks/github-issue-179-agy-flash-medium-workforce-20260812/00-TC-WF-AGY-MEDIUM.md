# Task Card: TC-WF-AGY-MEDIUM

artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: TC-WF-AGY-MEDIUM
source_issue: https://github.com/James3014/Nexus-new/issues/179
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
AUTO_CHAIN: false

## Objective

Add a distinct Agy workforce identity for `gemini-3.6-flash-medium` so exact Medium-bound Task Cards can pass Workforce Admission without redefining or substituting the existing `agy_flash / gemini-3.6-flash-high` worker.

## Allowed files

- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/services/test_model_workforce_policy_loader.py`
- `tasks/github-issue-179-agy-flash-medium-workforce-20260812/INDEX.md`
- `tasks/github-issue-179-agy-flash-medium-workforce-20260812/00-TC-WF-AGY-MEDIUM.md`

## Required behavior

- Add `agy_flash_medium` with provider `agy`, exact model `gemini-3.6-flash-medium`, state `REGISTERED_CONDITIONAL`, availability `AVAILABLE`, autonomy ceiling `L1`, and preferred context `nexus_bounded`.
- Permit only bounded implementation/candidate-generation and focused verification roles with Task Card, allowed-files, mandatory-command, parser/verifier, and independent-verification controls.
- Preserve `agy_flash -> gemini-3.6-flash-high` and default routing unchanged.
- Fail closed for High/Medium cross-binding and missing controls.
- Do not copy or relabel High benchmark/calibration evidence as Medium evidence.

## Forbidden scope

- No changes to `CapabilityPlanner`, `HybridRouteDecision`, worker adapters, Gateway, provider runtime, default routing, historical three-arm snapshot/matrix, or any Phase 1A implementation file.
- No L2 promotion, `PROVEN_MAINCHAIN`, runtime activation, approval, integration, protected merge, release, or production/public claim.

## Verification

```bash
uv run pytest -q tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
uv run python scripts/ops/select_tests.py --json nexus/config/model_workforce.yaml
uv run ruff check tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
uv run ruff format --check --preview tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

Also prove High admission remains valid, exact Medium admission is allowed only at L1/bounded context with full controls, cross-binding fails closed, default routing stays `agy_flash`, and provider+model identities remain unique.

## Claim ceiling

Before independent acceptance and merge: `IMPLEMENTER_PASS_PENDING_ACCEPTANCE` only.

After independent acceptance plus protected merge/readback, maximum claim: `agy_flash_medium_registered_conditional_l1`.

## Block classification

- `RECOVERABLE_BLOCK`: tooling or test-environment failure without contract contradiction.
- `HARD_BLOCK`: any implementation requires widening into routing, runtime adapters, High evidence inheritance, L2 promotion, or Phase 1A mutation.
