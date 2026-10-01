# TASK-001 — Persist transitional Nexus self-hosting authority policy

## Identity

- task_id: `nexus-self-hosting-authority-stabilization-20260902-001`
- campaign_id: `nexus-self-hosting-authority-stabilization-20260902`
- status: COMPLETE
- owner: James Chen
- contract_kind: TRACKED_TASK_CARD
- AUTO_CHAIN: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push_protected_refs: false

## Owner decision

Nexus remains in a self-hosting stabilization phase after G10. G10 proves that the NEXUS_GOVERNED path works; it does not make that path the mandatory default for all current Nexus development.

Until an explicit future Owner decision declares `NEXUS_GOVERNANCE_DEFAULT_READY`:

1. Bounded Owner-authorized `DIRECT_CANONICAL` and `DIRECT_DELEGATED` remain legitimate Nexus development lanes, including bootstrap, bounded environment reconstruction, repair/recovery, and ordinary bounded development that otherwise satisfies their existing lane constraints.
2. `NEXUS_GOVERNED` / governed execution is used where current governance contracts require it and for representative governed work/pilots, but G10 completion alone does not force a repository-wide default-lane cutover.
3. An execution that has entered a governed/NEXUS_GOVERNED attempt must never silently downgrade to direct/OWNER_DIRECT because authority is missing, stale, expired, unavailable, or transport fails. It must block, rebind, reconcile, or recover under a separately authorized action.
4. Current narrowly typed DevSpace `OWNER_DIRECT` bootstrap capabilities such as `workspace_clone` and `dependency_sync` are not considered policy defects merely because they are not yet NEXUS_GOVERNED.
5. `NEXUS_GOVERNANCE_DEFAULT_READY` is an Owner-gated milestone, not an automatic inference from G10, tests, an agent, a Task Card, or runtime state.

The readiness review should require evidence that representative real tasks work end to end under governed authority; continuation/timeout/reconcile/restart paths are exercised; Nexus can modify itself without routine authority recursion; Task Card/grant/admission/execution contracts are stable enough for normal work; common work no longer requires routine direct bypass; and the direct recovery path can restore the governance plane when needed.

After the Owner explicitly declares `NEXUS_GOVERNANCE_DEFAULT_READY`, a separate policy change may make governed execution the default and narrow direct authority. This Task Card does not settle that eventual permanent scope in advance.

## Allowed files

- `AGENTS.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`
- `docs/governance/current_operating_mode.yaml`
- `tests/ops/test_bootstrap_authority_files.py`
- `tasks/nexus-self-hosting-authority-stabilization-20260902/INDEX.md`
- `tasks/nexus-self-hosting-authority-stabilization-20260902/TASK-001.md`

## Forbidden scope

- No runtime or executable code changes.
- No DevSpace code changes.
- No standing-grant mutation.
- No CapabilityPlanner, Workforce Admission, lifecycle, schema, migration, production, release, or deployment changes.
- Do not declare `NEXUS_GOVERNANCE_DEFAULT_READY` in this task.
- Do not remove existing governed-required conditions from direct lanes.
- Do not make silent governed-to-direct fallback legal.

## Required policy effects

- Root repository authority must explicitly state the current self-hosting stabilization status and transition semantics.
- The detailed Task Execution Contract must match the root authority without creating a second authority model.
- The machine-readable current operating mode must preserve direct defaults during stabilization and explicitly require an Owner-gated future transition rather than treating G10 as automatic cutover.
- Preserve the distinction between Nexus execution lanes (`DIRECT_CANONICAL`, `DIRECT_DELEGATED`, `GOVERNED`) and DevSpace execution authority modes (`OWNER_DIRECT`, `NEXUS_GOVERNED`).
- Existing direct-lane safety/verification/scope constraints remain in force.
- Future default-authority transition remains an explicit Owner decision backed by evidence, not an automatic gate closure.

## Verification

- Review the exact diff for semantic consistency and scope.
- Verify all three authority surfaces contain no contradictory default-lane rule.
- Verify existing statements that route/lifecycle/workforce/security authority changes require governed handling remain intact.
- `tests/ops/test_bootstrap_authority_files.py` must assert the new transition and fail-closed semantics.
- `git diff --check` equivalent through repository CI / exact-head checks.
- All protected-branch required checks must be terminal success on the exact PR head before merge.

## Closure evidence

- Policy Candidate head: `eed4af89084a7d0cfe8f3320f26f7481550ee948`.
- Policy PR: #706, exact-head merged to `main` as `a770e60ac11ef950aba4042cc1631906e36f5576`.
- Focused bootstrap-authority regression: `tests/ops/test_bootstrap_authority_files.py` — 13/13 passed on the Candidate; `git diff --check` passed.
- Protected-main required checks on the exact Candidate head all completed successfully: `Exact-base impact gate`, `Trusted verifier (default branch)`, and `Full published Git history secret audit`.
- Policy diff changed only the six authorized repository artifacts: root authority, Task Execution Contract, current operating mode, focused regression test, campaign INDEX, and this Task Card. No runtime/executable code, DevSpace code, standing grant, Planner, Workforce, lifecycle, migration, deployment, release, or production authority was changed.
- Post-merge readback bound GitHub `main` to `a770e60ac11ef950aba4042cc1631906e36f5576` before this closure writeback.

## Exit criteria

COMPLETE. The three authority surfaces durably encode the Owner-approved stabilization policy; protected-main verification passed on the exact reviewed Candidate; the policy was merged to `main`; G10 remains proof of the governed path rather than an automatic default-lane cutover; and the future `NEXUS_GOVERNANCE_DEFAULT_READY` transition remains an explicit Owner decision.
