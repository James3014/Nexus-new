# Campaign: GitHub Issue #75 Deletion Provenance

- authority: GitHub Issue #75 and Owner comments
- status: COMPLETE
- task_id: github-issue-75
- base_sha: 3c4f9065739e7a718bc27e1bf0d0113150946c60
- historical_baseline: 3c4f9065739e7a718bc27e1bf0d0113150946c60
- reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- implementation_commit: 70fd467ab0d29f4373616a5e98d85b014efcd4de
- rebind_lineage_commit: d9e72df557493e249b54e7641d20ee314bc35646
- branch: codex/issue-75-deletion-provenance
- AUTO_CHAIN: false
- frontier: TERMINAL_RECONCILIATION
- frontier_status: COMPLETE
- completed_cards:
  - 01-exact-git-deletion-evidence.md
- blocked_cards: []
- terminal_marker: EXACT_GIT_DELETION_PROVENANCE_PROVEN
- claim_ceiling: EXACT_GIT_EVIDENCE_ONLY_PROVEN_ONLY

## Ordered cards

1. `01-exact-git-deletion-evidence.md` — COMPLETE (TERMINAL_RECONCILIATION)

## Physical evidence and terminal boundary

PR #118 physically merged exact head
`d9e72df557493e249b54e7641d20ee314bc35646` onto base
`d62310bf68ef44ca98664c47c22ed854a37d2caf` as
`70fd467ab0d29f4373616a5e98d85b014efcd4de`, with an exact six-file scope and
zero deletions. Five exact-head workflows completed successfully; protected
run `31481084538` and impact run `31481085768` are terminal PASS with
`EXACT_BASELINE_DEBT`, `blocking=false`, `new_failures=[]`,
`resolved_failures=[]`. The Owner receipts
`DESIGN_REVIEW_ACCEPTED_WITH_CLAIM_CEILING`,
`ISSUE_75_MONOTONIC_TEST_INVENTORY_CANDIDATE`, and
`ISSUE_75_EXACT_HEAD_ACCEPTANCE_PASS` are recorded on Issue #75, which is
closed `completed`. Current main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
readback confirms the implementation files remain present.

## Claim boundary

`EXACT_GIT_DELETION_PROVENANCE_PROVEN` is limited to the exact GitHub
collaboration deletion-provenance foundation at its merged head
(`EXACT_GIT_EVIDENCE_ONLY`). It grants no #104/#105/#106,
protected-ruleset/App enforcement, runtime, route, Workforce, lifecycle,
approval, integration, merge, release, or production authority. Evidence here
cannot authorize Candidate creation, approval, integration, cleanup, merge,
release, or production claims. `AUTO_CHAIN=false`.
