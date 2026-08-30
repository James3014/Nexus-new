# Task Card: TASK-PWS-001

task_id: `TASK-PWS-001`

Status: `ACTIVE`

Campaign: `CAMPAIGN-PLANNER-WORKFORCE-SELECTION-REPAIR-01`

Goal: repair the Planner/Workforce seam so elevated trust/evidence mutation is not misclassified as ordinary fast work, and the fast bounded default route cannot silently remain on a superseded model generation.

## Authority and claim ceiling

- Owner explicitly authorized this control-plane repair in the current thread.
- Exact external-bootstrap parent: `5d6bec64164bc2ff86b145cbf0a06dbbe5a75064`.
- This card exists because the affected selector cannot safely select the worker that repairs its own selection semantics.
- Authority includes only Planner demand classification, Workforce machine policy/docs coherence, invariant tests, a scoped repair commit, and independent verification.
- No Task3 Product semantics, Task4 authority/signing, merge, push, release, production, activation, public claim, or protected-main action.
- Implementer cannot approve, integrate, or independently accept its own Candidate.
- `AUTO_CHAIN=false`.

## Required behavior

1. Preserve `CapabilityPlanner` as the sole route/capability selector; do not add caller-selected worker authority.
2. Mutating trust, provenance, evidence-integrity, verification/certification authority, signing, receipt-binding, replay, or immutable-CAS contracts must resolve to `main_engineering`, not `fast_bounded_implementation`.
3. Ordinary simple bounded bugfixes must remain `fast_bounded_implementation`.
4. The online `fast_bounded_implementation` route must point to `agy_flash_37_medium / gemini-3.7-flash-medium` after exact policy admission.
5. `agy_flash_37_medium` becomes the current default for that role; `agy_flash / gemini-3.6-flash-high` remains an explicit previous-generation fallback and is not the default route.
6. Add a machine-verifiable coherence invariant: every direct online role route must resolve to an existing eligible worker that advertises the role and is marked current/default; a route to a conditional-only, previous, superseded, blocked, disabled, experiment-only, or quarantined worker fails tests.
7. Registering a successor generation without an explicit route disposition must fail policy verification rather than silently preserving a stale default.
8. Preserve exact identity separation; 3.6 and 3.7 must never be treated as interchangeable aliases.

## Allowed paths

- `nexus/engine/capability_planner.py`
- `nexus/services/model_workforce_policy.py`
- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/engine/test_capability_planner.py`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/services/test_mainchain_family_canary_matrix.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tasks/planner-workforce-selection-repair-20260830/INDEX.md`
- `tasks/planner-workforce-selection-repair-20260830/00-planner-workforce-selection-repair.md`

Maximum changed paths: `10`.

## Forbidden scope

- Product code or tests, `CandidateVerifier`, evidence bridge implementation, Task4, certification, signing, standing grants, approval, integration, merge, release, production, provider adapters, or account credentials.
- Caller-supplied worker/model override authority.
- Automatic promotion solely because a numerically newer model exists; current/default disposition must be explicit and policy-bound.
- Removal of Workforce Admission, model preflight, exact identity, parser/verifier, receipt, or independent verification gates.

## Mandatory RED

- Reproduce that a mutating trust/provenance/evidence-integrity task currently resolves to `fast_bounded_implementation`.
- Reproduce that the current fast route resolves to `agy_flash / gemini-3.6-flash-high` despite an admitted 3.7 worker.
- Add tests proving stale/non-current route mapping is rejected before changing production policy/code.

## Verification

- `uv run pytest -q tests/engine/test_capability_planner.py -k workforce_demand`
- `uv run pytest -q tests/contracts/test_model_workforce_policy.py tests/contracts/test_main_engineering_route_binding.py tests/services/test_mainchain_family_canary_matrix.py`
- `uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py -k workforce`
- `uv run ruff check nexus/engine/capability_planner.py tests/engine/test_capability_planner.py tests/contracts/test_model_workforce_policy.py`
- `uv run pyright nexus/engine/capability_planner.py`
- `git diff --check`
- Re-run the exact EPB Planner/Admission probe and prove it resolves `codex_luna / gpt-5.6-luna` while an ordinary bounded task resolves the 3.7 Agy worker.

## Exit

- Candidate must have exact parent/tree/diff and independent review.
- Repair completion does not integrate or activate it.
- Terminal: `PLANNER_WORKFORCE_SELECTION_REPAIR_VALIDATED` then STOP this bootstrap repair and resume normal governed execution only after separately bound source acceptance.

`AUTO_CHAIN=false`
