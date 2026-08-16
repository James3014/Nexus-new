# Task Card: TC-WF-AGY-MEDIUM

artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: TC-WF-AGY-MEDIUM
source_issue: https://github.com/James3014/Nexus-new/issues/179
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
AUTO_CHAIN: false
reconciliation: TERMINAL_RECONCILIATION

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

## Terminal reconciliation (2026-08-14)

This card is terminal. Historical objective, allowed files, required behavior, forbidden scope, verification commands, claim ceiling, and block classification above are preserved unchanged as the implementation baseline.

- Issue #179: CLOSED/completed 2026-08-12; Owner receipt `5261052608` (`MODEL_CALIBRATION_PREWRITEBACK_20260812`) binds `agy_flash_medium` = `agy / gemini-3.6-flash-medium`, `REGISTERED_CONDITIONAL`, `AVAILABLE`, `L1`, `nexus_bounded`, with `provider_model_revision: UNRESOLVED`.
- PR184: base `57d8e94f4548009b4322cfac93c6104e2fb95ca0` -> head `dd40921ebde7c0fe1dacb0d01056a89360adb513` -> merge `34fc70af1cd57f7499bf92ecec4926a9716c8de2`; changed exactly `nexus/config/model_workforce.yaml`, `docs/arch/MODEL_WORKFORCE_POLICY.md`, `tests/contracts/test_model_workforce_policy.py`, `tests/services/test_model_workforce_policy_loader.py`, plus this card and its INDEX; 6 files total, +204/-1; merged by Owner 2026-08-12; closes #179.
- PR184 head exact-base checks: 5/5 success (Pyright run 31564702745, Wiki Governance run 31564702729, Ruff run 31564702703, Bandit run 31564702739, Pytest run 31564702706).
- Current main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c` (PR #333 merge);
  previous reconciled snapshot `cdf2570ede5ae218f36f886b696c8da45458043a`
  retained as historical; merge ancestry verified via
  `git merge-base --is-ancestor`.
- Marker: `AGY_FLASH_MEDIUM_REGISTERED_CONDITIONAL_L1`.
- Claim ceiling: source/config/test evidence proven only. No provider/model call, no policy/route/runtime mutation, no L2 or `PROVEN_MAINCHAIN` claim, and no runtime, approval, integration, merge, release, or production authority.
