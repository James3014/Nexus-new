# ARCHIVED 2026-10-24 (Phase-2 deletion, item 6)

Physical deletion of the GitHub completion loop (`run_github_completion_loop`,
`GitHubCompletionPort`): a complete CAS-merge completion design (main-drift absorption across
bounded integration generations, durable standing-grant merge authorization, G07 issue closure
intent, post-merge reconciliation) that was never wired to production. Tracking issue: #2584
(stays open for the deferred items). Decision: Owner (James), 2026-10-24, "兩批都照建議刪"
(delete both batches as recommended; item 6: archive the design to knowledge first, write the
design doc with source paths and commits, then delete from Nexus-new; not moved into Cairnwork),
relayed by the coordinator, under the standing Phase-2 deletion approval of 2026-10-20. Plan v1
and the plan check (Codex) are on #2584. The originals are in git history at `origin/main`
5de9b1f94baf9eff02a28f7ca2e5b7c382d3d829.

Design archive: knowledge repo (James3014/knowledge) `a8ec6bd`,
`nexus/architecture/2026-10-24-github-completion-loop-retired-design.md` (purpose, public API,
step-by-step control flow with constants and reason codes, the 15-method port contract, the
invariants the 93 tests asserted, dependencies, restore command).

Evidence (the 10-20 evidence at 01dc1015, re-run on 5de9b1f94 before deleting):
- `git grep` of the module path (dotted and slash) and every public name over the whole tree:
  no caller outside the module and its own test; the only registry entry is
  `tests/architecture/test_effect_owner_uniqueness.py` (MERGE_PORT / MERGE_LOOP); docs mention it
  in `docs/agents/TASK_EXECUTION_CONTRACT.md` and `docs/testing/test_impact_map.md`; historical
  Task Cards under `tasks/issue-1384-*` and the golden replay corpus mention the path as text and
  are left unchanged (replay corpus);
- sibling repos nexus-core, nexus-runtime, nexus-learning, devspace, repo-learning,
  nexus-open-swe-runtime, repository-intelligence-engine, nexus-opencli-reviewer,
  nexus-workbench, nexus-deployment-lab and cairnwork (freshly fetched `origin/HEAD`): none;
- Mac mini and M4 `~/.local/bin` and `~/Library/LaunchAgents`: none;
- the live Gateway does not load the module.

## Deleted

| file | lines | callers on main |
| --- | --- | --- |
| `nexus/orchestrator/github_completion_loop.py` | 1653 | none |

What this retires is a design and its test coverage, not live protection: merges are done by the
author with `gh pr merge --squash --match-head-commit`, behind the ruleset's required checks,
`Deletion guard`, `scripts/ops/trusted_merge_lane_gate.py` and
`issue_closure_guard.validate_final_merge_intent_binding` (both kept, both with production users)
and the review-record check.

## Kept (possible new orphans, not in this decision)

The loop was the only non-test user of `CandidateBlobEquivalence` and
`compute_candidate_equivalence_proof_hash` (`nexus.contracts.github_orchestration`),
`requalify_main_movement` and `resolve_durable_merge_authorization`
(`nexus.orchestrator.github_orchestration`) and `verify_post_merge_state`
(`nexus.services.issue_closure_guard`). They stay: they are outside the Owner's item-6 decision
and need their own evidence (phase-3 candidates).

## Registry and doc edits

- `tests/architecture/test_effect_owner_uniqueness.py` (#947 single effect owner): MERGE_PORT and
  MERGE_LOOP become `RETIRED` records, removed from `DECLARED` and `EDGES`. The merge scan no longer
  exempts the retired loop id: any `cas_merge` / `merge_pull_request` / `git_merge_pull_request`
  caller in `nexus/` or `scripts/ops/` fails. The inventory reports `protected_github_merge` as
  `{"classification": "RETIRED", "retired_boundary": ..., "retired_owner": ...,
  "physical_sink": None}` (schema string unchanged; no consumer outside the test). New controls:
  `test_github_merge_effect_is_retired`, `test_recreated_retired_merge_loop_symbol_fails` (exact
  retired path and symbol). The existing hostile controls are unchanged.
- `docs/agents/TASK_EXECUTION_CONTRACT.md`: the `github_complete_pull_request` paragraph no longer
  says the action binds `run_github_completion_loop()`; it says no implementation is wired today.
- `docs/testing/test_impact_map.md`: the `github_orchestration.py` row drops the deleted test path.

## Tests

- Deleted (every case exercised deleted code): `tests/nexus/orchestrator/test_github_completion_loop.py`
  (93 tests).
- Kept files keep every test id.
- New guard `tests/services/test_archived_phase2_item6_2026_10_24.py`: the module (and a `.py.bak`
  copy) stays absent and unimportable, nothing under `nexus/` or `scripts/` imports or names it or
  its public types, the live modules it imported stay, and the scans flag every import and naming
  form (non-vacuous control).

## Restore

`git show 5de9b1f94:nexus/orchestrator/github_completion_loop.py`. Re-adding it fails the guard
test and the effect-owner test on purpose; update both in the same PR.
