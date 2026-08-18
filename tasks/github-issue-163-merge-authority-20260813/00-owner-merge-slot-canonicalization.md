---
artifact_authority: historical
task_id: github-issue-163-owner-merge-slot-canonicalization
campaign_id: github-issue-163-merge-authority-20260813
source_issue: "#163"
owner: James Chen
status: SUPERSEDED
baseline_revision: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
superseded_by: tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md
---

# Owner merge-slot authority canonicalization

## Historical Objective

Make protected GitHub merge authority singular and unambiguous: standing
coordinator authority covers bounded pre-merge work; this card incorrectly
required a fresh Owner `MERGE_SLOT_GRANTED` decision at every protected merge.
That per-phase rule is superseded. Exact verification, branch protection,
scope/deletion checks, and expected-head/CAS remain mandatory.

## Inputs and dependencies

- Issue #163 latest Owner authority frontier.
- Current `main` at the exact baseline above.
- Existing GitHub collaboration and local lifecycle domain separation.
- Issue #8 remains downstream and must not be activated by this card.

## Allowed files

- `AGENTS.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`
- `.agents/skills/nexus-merge-gate/SKILL.md`
- `tests/ops/test_bootstrap_authority_files.py`
- `tasks/standing-owner-autonomy-20260811/INDEX.md`
- `tasks/standing-owner-autonomy-20260811/01-standing-coordinator-authority.md`
- this card and campaign `INDEX.md`

## Forbidden scope

- No merge API, GitHub adapter, lifecycle, route, Workforce, approval,
  integration, release, or production mutation.
- No implementation of the pre-merge standing-grant consumer in this card.
- No Issue #8 activation and no work on #143 or #191 and its dependency chain.

## Verification and evidence

- `python3 -m pytest -q tests/ops/test_bootstrap_authority_files.py`
- `git diff --check`
- exact eight-file scope audit and independent review

## Exit and residual debt

Exit with historical evidence only. The implementation and consumer are now
recorded by the superseding standing-grant artifact; #8 remains independently
governed and is not activated by this record.

Claim ceiling: `OWNER_MERGE_SLOT_AUTHORITY_CANONICALIZED_CANDIDATE_ONLY`.

`HARD_BLOCK` on authority widening, merge execution, unexpected overlap, or
required-check failure. `RECOVERABLE_BLOCK` for formatting/test defects.
