# Task Card: TASK-PWS-COMBINED-R2 — Learning/Core Workforce route repair

task_id: `TASK-PWS-COMBINED-R2`

Status: `ACTIVE`

Campaign: `CAMPAIGN-PLANNER-WORKFORCE-SELECTION-REPAIR-01`

Mission: `CORE-EVIDENCE-TRUST-CANONICALIZATION-20260902`

## Authority and exact base

- Owner resolution: `RESOLVE WORKFORCE OVERLAP AND CONTINUE`.
- Repository: `James3014/Nexus-new`.
- Exact base commit: `83353b5ff0c44b2611a45dc7ba9853b6dfe93d44`.
- Exact base tree: `b6092bab54f745971146cf97ac67a699c10492b9`.
- Core predecessor: `TASK-PWS-001`, RED-only historical branch.
- Learning lineage: accepted Candidate
  `a9a560400501811ef9018179a8e62fa8a6ab984f`, local integration evidence only.
- Historical PR #668 remains reference evidence only.

This Card creates no second selector. `CapabilityPlanner` remains the sole
route/capability-selection authority; Workforce policy constrains eligible
workers and resolves only Planner-derived Workforce demands.

## Required combined behavior

1. Bind global `routing.online.fast_bounded_implementation` to exact worker
   `agy_flash_37_medium / gemini-3.7-flash-medium`.
2. Mark `agy_flash_37_medium` as the sole admissible `CURRENT_DEFAULT` for
   that direct role and mark `agy_flash / gemini-3.6-flash-high` as `FALLBACK`.
3. Require each direct route target to exist, be available/admissible, and
   advertise the routed role.
4. Reject stale fallback routes, multiple current defaults, non-admissible
   current defaults, and registered successors without explicit disposition.
5. Preserve exact 3.6/3.7 identity separation and all unrelated roles/routes.
6. Preserve the Learning exact campaign constraint for
   `CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01` resolving
   `fast_bounded_implementation` to `agy_flash_37_medium`.
7. Campaign resolution is exact-match only; blank, missing, prefixed, or
   unrelated campaign IDs use the global route.
8. Derive campaign identity from verified Card content or an authenticated
   explicit parameter, retaining safe legacy path fallback only where already
   supported. Task-ID prose/prefix alone cannot mint campaign identity.
9. Reject caller-supplied `worker` and `worker_id` identity overrides.
10. Preserve PR #727 `normalize_online_policy` and Planner `budget` data flow.
11. Preserve integrity-sensitive `main_engineering` precedence with regression
    witnesses only; do not modify `capability_planner.py` production.

## Allowed paths

- `nexus/config/model_workforce.yaml`
- `nexus/services/model_workforce_policy.py`
- `nexus/engine/canonical_task_seam.py`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/services/test_model_workforce_policy_loader.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/engine/test_capability_planner.py`
- `tests/services/test_mainchain_family_canary_matrix.py`
- `tasks/planner-workforce-selection-repair-20260830/INDEX.md`
- `tasks/planner-workforce-selection-repair-20260830/00-planner-workforce-combined-repair.md`

Maximum changed paths: `11`.

## Forbidden scope

- `nexus/engine/capability_planner.py` production changes.
- Any second selector/router/planner or caller-selected worker/model authority.
- Lifecycle, Candidate, receipt, standing-grant, approval, integration,
  provider-adapter, credential, cleanup, release, or production changes.
- Weakening Workforce Admission, exact identity, fail-closed, security, or
  independent-verification gates.
- Wholesale cherry-pick/merge of stale Core, Learning, or PR #668 branches.

## Required RED/GREEN and hostile witnesses

RED must demonstrate current main lacks the combined behavior. GREEN must cover:

- canonical global route and exact campaign constraint;
- exact campaign match, blank/missing/unrelated fallback, and prefix rejection;
- caller worker/worker_id mismatch rejection;
- stale fallback, missing role, missing disposition, non-admissible default,
  unknown campaign worker, and duplicate-current-default rejection;
- unaffected roles/routes and Planner integrity-sensitive precedence;
- Gateway end-to-end selection derived from Planner/admission, not caller prose.

## Verification

- `uv run pytest -q tests/contracts/test_model_workforce_policy.py`
- `uv run pytest -q tests/services/test_model_workforce_policy_loader.py`
- focused affected tests in `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `uv run pytest -q tests/engine/test_capability_planner.py -k workforce_demand`
- `uv run pytest -q tests/services/test_mainchain_family_canary_matrix.py`
- Ruff on all changed Python files.
- Pyright on changed production Python files.
- `git diff --check`

## Exit and claim ceiling

The worker produces implementation evidence only. It cannot approve, integrate,
merge, push, clean up, release, activate runtime, or make a public/production
claim. Independent acceptance binds exact base/head/tree/Card hash and reruns
the required checks.

Terminal for this bounded unit:

`PLANNER_WORKFORCE_COMBINED_REPAIR_CANDIDATE_VERIFIED`

`AUTO_CHAIN=false`
