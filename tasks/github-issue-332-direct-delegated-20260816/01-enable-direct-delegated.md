# TASK-332-001 — Enable bounded DIRECT_DELEGATED authority without changing merge authority

- **Campaign:** `CAMPAIGN-NEXUS-332-DIRECT-DELEGATED-20260816`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-NEXUS-332-DIRECT-DELEGATED`
- **Source spec SHA-256:** `9d101c32dd559f4bf14713d49bb79e45dc1c0b1ad00157fa7319eb8d03de1f7a`
- **Source groups:** `TG-001`
- **Requirements:** `REQ-001; REQ-002; REQ-003; REQ-004; REQ-005`
- **Acceptance:** `AC-001; AC-002; AC-003; AC-004; AC-005; AC-006`
- **Auto-chain:** `false`
- **Maximum claim:** `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY`
- **Depends on:** `none`
- **Dependency unlock evidence:** `none`
- **Task type:** `CONTRACT`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `DIRECT_TYPED_ACTIONS`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Implement the settled Issue #332 authority delta on a clean current-main-derived issue branch: add one bounded `DIRECT_DELEGATED` lane and its tests while preserving the pre-existing #163 protected-merge contract without semantic weakening.

## Observable outcome

One bounded Candidate makes `DIRECT_DELEGATED` explicit while leaving #163 protected-merge authority unchanged.

## Non-goals

No CapabilityPlanner or route change; no Nexus lifecycle implementation change; no Workforce policy/model promotion; no runtime provider selection change; no CI workflow redesign; no branch-protection or merge-authority rewrite; no test skip/xfail/assertion weakening; no direct push to `main`; no approval, integration, merge, release, production-data action, production claim, or public claim; no successor-task auto-chain.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-001 | implementation requirement | explicit Owner-selectable one-milestone `DIRECT_DELEGATED` lane |
| REQ-002 | implementation requirement | bounded one-worker lane, independent verification, fail-closed escalation, `AUTO_CHAIN=false` |
| REQ-003 | implementation requirement | non-Nexus external identity binding does not inherit Nexus Workforce Admission |
| REQ-004 | preservation requirement | exact #163 merge-slot semantics remain unchanged |
| REQ-005 | physical-scope requirement | only authorized semantic and governance-metadata files change |
| AC-001 | acceptance witness | lane explicit and delegation alone is not an unconditional governed trigger |
| AC-002 | acceptance witness | one-worker/identity/isolation/retry/STOP boundaries fail closed |
| AC-003 | acceptance witness | external binding grants no Nexus authority and Nexus runtime admission remains mandatory |
| AC-004 | acceptance witness | `MERGE_SLOT_GRANTED`, `MERGE_INTENT`, exact repo/PR/head/base, drift invalidation, checks and CAS remain |
| AC-005 | acceptance witness | complete diff contains only allowlisted paths and no deletion |
| AC-006 | acceptance witness | focused verification, exact-head required CI, and independent acceptance are current |
| DEC-001 | owner decision | add bounded direct-delegated lane |
| DEC-002 | owner decision | preserve #163 protected-merge semantics exactly |
| DEC-003 | owner decision | only minimum governance metadata is allowed |
| CON-001 | authority constraint | protected merge remains a separate exact Owner slot |
| REJ-001 | rejected alternative | broader generic Owner integration authority must not enter this Candidate |

## Owner decisions

- `DEC-001`: add one bounded Owner-authorized non-Nexus direct-delegation lane.
- `DEC-002`: preserve exact #163 protected-merge semantics and authority separation.
- `DEC-003`: keep governance metadata and semantic scope minimal.

## Source and start state

- **Workspace/root:** `James3014/Nexus-new` GitHub collaboration repository
- **Branch:** `codex/issue-332-direct-delegated`
- **Starting HEAD:** `cc88519b314a782785ec2703a87f458bde5d4625`
- **Dirty baseline:** clean issue branch created exactly from starting HEAD with zero branch-relative diff before governance-metadata bootstrap
- **Required initial verification:** re-fetch `main` and `codex/issue-332-direct-delegated`; prove branch parent/baseline identity and no unexpected changed/deleted paths before each semantic file mutation
- **Freshness rule:** re-read current `main`, issue-branch head, target file blob SHA, Issue #332, and #163 preservation evidence immediately before material mutation; any unexpected drift fails closed for reconciliation

## MCP execution profile

- **App/server and action snapshot:** ChatGPT GitHub connector, repository-bound typed action surface for `James3014/Nexus-new`, observed 2026-08-16; no broad shell execution surface is authorized by this card
- **Exact required actions:** `fetch; fetch_file; create_blob; create_tree; create_commit; update_ref; compare_commits; create_pull_request; list_pr_changed_filenames; fetch_pr_patch`
- **Confirmation-required actions:** `none`
- **Idempotency and attempt rule:** every content update is blob/commit/ref identity-bound; `update_ref` uses `force=false`; after any ambiguous result re-fetch branch head and target content before deciding whether a retry is safe; never blindly replay a successful commit/ref mutation
- **Reconnect reconciliation:** re-fetch branch head, current `main`, complete changed-path set, and target file blobs; continue only when they match the same bounded Candidate lineage
- **Transport blocker:** `none`

## Authority map

- **Selection authority:** Owner Issue #332 and current continuation instruction; the validated spec fixes semantics and this Task Card fixes the bounded execution slice.
- **Execution authority:** primary coordinator may mutate only the allowlisted issue-branch paths through typed GitHub actions and may open a Candidate PR; no delegated worker is required for this one-time authority change.
- **Verification authority:** primary coordinator must inspect the complete physical diff and current check evidence; exact Candidate acceptance is independently performed under the acceptance-audit workflow.
- **Receipt authority:** Git commit/tree/diff, PR head/base, exact check/run evidence, and acceptance receipt may support Candidate-only claims.
- **Approval/integration authority:** excluded; protected merge remains exclusively under current #163 fresh exact Owner `MERGE_SLOT_GRANTED` authority and expected-head/CAS after independent acceptance.

## Allowed scope

- **Read:** `AGENTS.md; docs/agents/TASK_EXECUTION_CONTRACT.md; docs/agents/WORKFORCE_EXECUTION_OVERLAY.md; .agents/skills/nexus-merge-gate/SKILL.md; tests/ops/test_bootstrap_authority_files.py; tests/ops/test_bootstrap_context_budget.py; docs/specs/ISSUE_332_DIRECT_DELEGATED.md; tasks/github-issue-332-direct-delegated-20260816/INDEX.md; tasks/github-issue-332-direct-delegated-20260816/01-enable-direct-delegated.md`
- **Edit:** `AGENTS.md; docs/agents/TASK_EXECUTION_CONTRACT.md; docs/agents/WORKFORCE_EXECUTION_OVERLAY.md; tests/ops/test_bootstrap_authority_files.py; tests/ops/test_bootstrap_context_budget.py`
- **Create:** `docs/specs/ISSUE_332_DIRECT_DELEGATED.md; tasks/github-issue-332-direct-delegated-20260816/INDEX.md; tasks/github-issue-332-direct-delegated-20260816/01-enable-direct-delegated.md`
- **Delete:** `none`
- **Maximum touched production files:** `6`
- **Maximum touched test files:** `2`

## Unknown scan

- **Known facts:** baseline/current-main authority makes delegated implementation an unconditional direct-to-governed escalation trigger; Workforce Admission remains Nexus-runtime authority; #163 exact merge-slot semantics are current and binding; PR #320 contains rejected merge-policy drift.
- **Assumptions requiring verification:** current `main` and issue-branch lineage remain compatible; exact-head GitHub CI remains available after PR creation; connector ref writes remain fast-forward/CAS-safe.
- **Architecture risks:** accidentally importing PR #320 wholesale could weaken protected merge authority or create a second authority surface.
- **Evidence risks:** a passing subset or stale PR head can appear green; bootstrap authority tests must directly witness the workforce-overlay boundary and existing merge-slot assertions must remain intact; exact-head required CI and independent acceptance remain mandatory.
- **Missing owner decision:** `none`

## Mandatory source audit

Read current-main versions of root `AGENTS.md`, `docs/agents/TASK_EXECUTION_CONTRACT.md`, `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`, the existing merge-slot assertions in `tests/ops/test_bootstrap_authority_files.py`, the context-budget guard in `tests/ops/test_bootstrap_context_budget.py`, and `.agents/skills/nexus-merge-gate/SKILL.md` as a read-only preservation witness. Compare PR #320 only as historical evidence; never use it as the implementation base or authority. Audit complete changed/deleted paths against the eight-path mutation allowlist.

## Start-state classification

`POLICY_CONFLICT`

## RED or existing-guard proof

At the exact baseline, root/task execution authority treats delegated implementation as a reason to escalate direct work to governed execution, conflicting with settled `DEC-001`; at the same baseline, the existing protected-merge guard requires exact `MERGE_SLOT_GRANTED`/`MERGE_INTENT` semantics and must continue to pass unchanged. The change is therefore a bounded policy-contract delta with an existing negative merge-authority guard, not a runtime defect claim.

## Implementation constraints

Implement selectively from current `main`; do not copy PR #320 wholesale. Add only the minimum direct-delegation definitions, eligibility/escalation rules, external identity boundary, and tests required by REQ-001 through REQ-003. Preserve all existing #163 merge paragraphs and assertions semantically; do not replace exact merge-slot language with generic integration-authority wording. Preserve unrelated source and dirty state. No runtime code, workflow file, route, lifecycle, Workforce policy, migration/schema, or protected-ref mutation is permitted.

## GREEN and regression gates

- AC-001: root/task contract explicitly define `DIRECT_DELEGATED`, and delegation alone is no longer an unconditional governed trigger when the lane conditions hold.
- AC-002: tests witness exactly one bounded external worker/task, direct identity binding, isolation/session reconciliation, independent coordinator verification, STOP, `AUTO_CHAIN=false`, prohibited worker authorities, and stable `DIRECT_DELEGATED_BLOCKED` behavior.
- AC-003: workforce overlay and bootstrap authority tests prove non-Nexus direct delegation does not use Nexus Workforce Admission while Nexus runtime still requires it and external binding grants no Nexus authority.
- AC-004: existing merge-slot assertions for fresh exact `MERGE_SLOT_GRANTED`, `MERGE_INTENT` evidence-only semantics, repo/PR/head/base binding, drift invalidation, required checks, and expected-head/CAS remain present and passing; no generic integration-authority substitution appears.
- AC-005: complete diff/path audit shows exactly the five semantic files plus three authorized governance metadata files, with zero deletions and no CI/runtime/product drift.
- AC-006: focused authority/context tests, `git diff --check`, exact-head required GitHub CI, and independent Candidate acceptance are all current and successful before merge consideration.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| V1 | TARGET_ROOT | `python3 -m pytest -q tests/ops/test_bootstrap_authority_files.py tests/ops/test_bootstrap_context_budget.py` | focused direct-delegation, merge-authority, workforce-overlay, and L0 context witnesses | exit 0; all selected tests pass |
| V2 | TARGET_ROOT | `git diff --check cc88519b314a782785ec2703a87f458bde5d4625 HEAD` | whitespace/error audit for complete Candidate delta | exit 0; no diff-check findings |
| V3 | TARGET_ROOT | `git diff --name-status cc88519b314a782785ec2703a87f458bde5d4625 HEAD` | complete changed/deleted-path audit | only the eight authorized paths; zero deletions |
| V4 | TARGET_ROOT | `git grep -n MERGE_SLOT_GRANTED AGENTS.md docs/agents/TASK_EXECUTION_CONTRACT.md tests/ops/test_bootstrap_authority_files.py` | negative-control presence for exact Owner merge-slot authority | required merge-slot witnesses remain present |
| V5 | TARGET_ROOT | `git grep -n MERGE_INTENT AGENTS.md docs/agents/TASK_EXECUTION_CONTRACT.md tests/ops/test_bootstrap_authority_files.py` | negative-control presence for evidence-only merge intent | required merge-intent witnesses remain present |

## Physical evidence

Bind the final issue-branch commit and tree; exact base/main SHA; complete changed/deleted path set; per-file diff; PR number/head/base; focused verifier commands and exit evidence when available; exact-head required GitHub Actions run/job conclusions; and independent acceptance receipt. Distinguish repository source/test Candidate evidence from current-main authority, loaded runtime, release, or production evidence. No Candidate-only evidence may be promoted beyond `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY`.

## Independent review

A fresh independent Candidate acceptance must bind the exact PR head/base/commit/tree/diff and review the validated spec, Issue #332, #163 preservation contract, full changed-path set, authority semantics, negative merge controls, focused tests, CI evidence, and claim ceiling. The implementer/coordinator may not self-convert implementation evidence into acceptance, approval, integration, merge, release, or production truth.

## Exit conditions

- **PASS:** one exact Candidate PR contains only the authorized eight-path delta, satisfies AC-001 through AC-006 with current evidence, and receives independent Candidate acceptance; implementation then stops before protected merge.
- **BLOCK:** any authority widening, merge-slot weakening, out-of-scope path/deletion, stale/failed required verifier, incompatible current-main drift, ambiguous connector mutation, or evidence gap prevents Candidate PASS and fails closed for reconciliation.
- **Residual debt:** protected merge still requires a fresh exact #163 Owner `MERGE_SLOT_GRANTED`; after any authorized merge, current-main readback is still required before `DIRECT_DELEGATED` can be claimed as repository authority.
- **Next gate:** independent Candidate acceptance, then the separate exact protected-merge Owner slot; no auto-chain.
