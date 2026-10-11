# Planner / Runtime Layering — Wave 2

**Authority ceiling:** architecture/implementation boundary; no merge/release/deployment authority.

## Current ownership

- `James3014/Nexus-new` owns the current `CapabilityPlanner` route/capability authority and the canonical host planner-domain contracts used by Nexus-new.
- `James3014/nexus-runtime` owns execution coordination, retry/replan state, writer/effect boundaries, durable context/state, and explicit composition.
- Runtime may carry a packaged planner implementation for standalone qualification/compatibility, but that implementation is not a second Nexus route authority.

## Phase 4b source ownership (D2)

`James3014/nexus-runtime` is the planner *source* owner; Nexus-new keeps route/capability *decision* authority through issue binding. All 27 duplicated planner modules in Nexus-new are now `install_alias` shims of `nexus_runtime.planning.*` / `nexus_runtime.support.*` (paths kept, no deletions; runtime 758132f, which synced #1737 and #1579). `runtime_compat` no longer injects planner factories. The runtime takes no repository-relative paths: Nexus-new passes its root explicitly (`nexus/core/repo_root.py`) as `shared_playbook_root` to `build_runtime_exports`, every `CapabilityPlanner(...)`, the canonical planning seam, and `bind_shared_playbook_runtime_receipts(root=...)`; without a root the runtime records `SHARED_PLAYBOOK_ROOT_UNCONFIGURED` instead of guessing (`tests/architecture/test_planner_alias.py`, `tests/architecture/test_planner_source_owner.py`).

## Complete host binding

`nexus.services.runtime_compat` binds the following six symbols as one family:

1. `CapabilityPlanner`
2. `CanonicalPlanningBundle`
3. `CanonicalTaskContext`
4. `ExecutionReplanAuthorization`
5. `plan_canonical_task_bundle`
6. `replan_canonical_task_bundle`

The matching Runtime Wave-2 contract rejects partial external planner-domain overrides so a host Planner cannot be silently mixed with packaged plan/replan/context semantics.

## HARD vs SOFT responsibility

Wave 2 adds `nexus.planner.responsibility.v1` without changing current selection behavior.

HARD obligations cover authority/scope/risk/evidence/verifiers/stop/replan/effect-retry safety. SOFT strategies cover decomposition, swarm/multi-agent topology, committee/judge strategy, research, context compression, and repair strategy.

SOFT strategies may never override HARD obligations.

This wave intentionally does not add HARD/SOFT fields to serialized `CapabilityPlan`; changing the plan payload here would also change plan hashes and receipt bindings. Strategy optionalization is a later behavioral gate after this ownership layer is accepted.
