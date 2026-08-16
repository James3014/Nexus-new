---
artifact_authority: current
task_id: github-issue-163-owner-merge-slot-canonicalization
campaign_id: github-issue-163-merge-authority-20260813
source_issue: "#163"
owner: James Chen
status: ACTIVE
baseline_revision: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
frontier: CANDIDATE_PENDING_OWNER_RECONCILIATION
terminal_disposition: KEEP_OPEN
mutation_authorized: false
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
historical_reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
marker: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED
claim_ceiling: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED
---

# Owner merge-slot authority canonicalization

## Objective

Make protected GitHub merge authority singular and unambiguous: standing
coordinator authority covers bounded pre-merge work; every protected merge
requires a fresh Owner `MERGE_SLOT_GRANTED` decision bound to exact repository,
PR, head, and base. Drift invalidates the slot.

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

Exit with a Candidate PR only. Issue #163 remains OPEN and no Owner terminal
disposition exists; this card is `CANDIDATE_PENDING_OWNER_RECONCILIATION`
candidate evidence, not a terminal claim. The candidate records the canonical
split: `GITHUB_MERGE` always returns `OWNER_MERGE_SLOT_REQUIRED`, the standing
grant is evidence-only with `mutation_authorized=false`, and protected merge
requires a fresh Owner `MERGE_SLOT_GRANTED` bound to exact repository, PR,
head, and base. Drift invalidates the slot.

Candidate evidence binds PR222 head `ff483f263cc603aea98ae7c38ca4c0ec56d1b1d7`
-> merge `e900ed6df092aac2d2333cc1db74f499a5881e7f`; PR223 head
`6536a749203fcae11d18f8894650fa0d82e495b5` -> merge
`f2f808166e735e271c793c6e939af8071d985cff`; PR234 consumer head
`87998b0e1c555170b91062e902d6a9c5aae36a21` -> merge
`8e0986b40db56016c79b03eb81ff3d03c85c6f32`. Historical checks: 92 focused
tests, Ruff, `git diff --check`, and independent acceptance; no live CI claim.
#8 and #17 remain separate. KEEP_OPEN until fresh independent acceptance and an
Owner terminal disposition; no merge without a fresh Owner
`MERGE_SLOT_GRANTED`.

Claim ceiling: `CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED`
(candidate evidence only).

`HARD_BLOCK` on authority widening, merge execution, unexpected overlap, or
required-check failure. `RECOVERABLE_BLOCK` for formatting/test defects.
