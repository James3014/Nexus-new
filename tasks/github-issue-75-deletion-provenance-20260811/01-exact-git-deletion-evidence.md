# Task Card: Issue #75 Exact-Git Deletion Evidence Foundation

- task_id: github-issue-75
- issue: #75
- status: COMPLETE
- base_sha: 3c4f9065739e7a718bc27e1bf0d0113150946c60
- historical_baseline: 3c4f9065739e7a718bc27e1bf0d0113150946c60
- reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- frontier_status: TERMINAL_RECONCILIATION
- terminal_marker: EXACT_GIT_DELETION_PROVENANCE_PROVEN
- claim_ceiling: EXACT_GIT_EVIDENCE_ONLY_PROVEN_ONLY
- implementation_commit: 70fd467ab0d29f4373616a5e98d85b014efcd4de
- rebind_lineage_commit: d9e72df557493e249b54e7641d20ee314bc35646
- worker_role: luna_worker
- autonomy: bounded CI implementation
- target: /private/tmp/nexus-issue75-luna-019fee
- AUTO_CHAIN: false

## Objective

Add a fail-closed, exact-Git-provenance path for deletion-only impact evidence
and exact-head test execution metadata. The only qualified result is
`EXACT_GIT_EVIDENCE_ONLY`; it never becomes a trusted cleanup/merge bypass.

## Dependencies and current trigger

- #88 / PR #97 is physically merged.
- #54 / PR #86 is physically merged.
- PR #87 at exact head `f1c2a2ecbbac6e916a7486b8b9bad5b5a1e1a615`
  currently reports identical base/head failures and no new failures but is
  correctly blocked as `IMPACT_UNKNOWN` because execution metadata is not a
  trustworthy exact-base comparison.
- Owner comment explicitly supersedes waiting for #71 before #75 mutation.

## Allowed files

Maximum five implementation/test/workflow files:

1. `scripts/ops/select_tests.py`
2. `scripts/ops/pr_impact_gate.py`
3. `.github/workflows/pytest.yml`
4. `tests/ops/test_select_tests.py`
5. `tests/ops/test_pr_impact_gate.py`

Campaign authority artifacts are outside that ceiling.

## Required behavior

- Compute from exact immutable base commit/tree, target commit/tree, and test
  inventory/tree; reject symbolic/mutable source identities.
- Parse two independently produced
  `git diff --raw -z --no-renames` NUL streams. Malformed, truncated,
  duplicate, ambiguous, or divergent evidence remains UNKNOWN/blocking.
- Require an explicit allowed-deletion manifest and recomputed orphan evidence
  for every deletion path. Any unexpected addition, executable replacement,
  missing manifest, path drift, stale source, tamper, parser gap, external
  launcher uncertainty, or unresolved dynamic dispatch remains UNKNOWN.
- Replacement is an exact permitted one-to-one relation; deletion plus
  addition is never implicitly a rename.
- Bind Tier-3/test evidence to exact source revision, collection count,
  pass/fail/error/skip node IDs, verifier digest, and terminal status.
- Preserve current exact-base comparison and fallback semantics.
- Return only `EXACT_GIT_EVIDENCE_ONLY`; never `verified`, `PROVEN`,
  `candidate_commit_allowed`, `public_claim_allowed`, or merge authority.
- Add a negative integration test proving the result cannot satisfy
  `resolve_attempt()` or Candidate creation.

## Forbidden scope

- PR #71/#87 product deletions, impact-map best-effort rows, admin/manual green,
  second classifier/map, lifecycle/Candidate/approval/integration/cleanup
  mutation, protected-base ruleset enforcement, CAS apply, release, or
  production claims.
- Imports/calls from CandidateVerifier, resolve_attempt, CandidateCommitter,
  approval/integration/cleanup services, or lifecycle mutation.

## Exact verification

```bash
uv run pytest -q \
  tests/ops/test_pr_impact_gate.py \
  tests/ops/test_select_tests.py
uv run ruff check \
  scripts/ops/select_tests.py \
  scripts/ops/pr_impact_gate.py \
  tests/ops/test_select_tests.py \
  tests/ops/test_pr_impact_gate.py
uv run python -m compileall -q \
  scripts/ops/select_tests.py \
  scripts/ops/pr_impact_gate.py \
  tests/ops/test_select_tests.py \
  tests/ops/test_pr_impact_gate.py
git diff --check
git diff --name-only 3c4f9065739e7a718bc27e1bf0d0113150946c60...HEAD
```

Required RED-to-GREEN tests cover malformed/duplicate/divergent raw streams,
stale SHA/tree/test inventory, missing/tampered manifests, implicit
replacement, unknown dynamic caller universe, metadata node/digest/status
drift, result-authority ceiling, and lifecycle/Candidate non-consumption.

## Exit and residual debt

- Exact five-file scope, scoped commit, card SHA binding, independent hostile
  review, exact-head CI.
- Maximum claim: an exact-Git evidence verifier can classify the tested
  deletion-only evidence without weakening UNKNOWN. It does not itself prove
  orphan status, authorize deletion, satisfy Candidate/approval/integration,
  or make PR #71/#87 merge-authoritative.
- Create durable follow-ups for protected workflow verification and required
  ruleset/App enforcement before any cleanup result can become authoritative.

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation/test defect.
- `HARD_BLOCK`: authority leakage, need for product/lifecycle mutation,
  inability to recompute immutable Git facts, or any request to weaken UNKNOWN.

## Physical evidence and terminal boundary

- Historical baseline (Task Card): `3c4f9065739e7a718bc27e1bf0d0113150946c60`.
- PR #118 base: `d62310bf68ef44ca98664c47c22ed854a37d2caf`.
- PR #118 head: `d9e72df557493e249b54e7641d20ee314bc35646`.
- PR #118 merge: `70fd467ab0d29f4373616a5e98d85b014efcd4de` (merged by the
  Owner on 2026-08-11; closes Issue #75).
- Exact scope: six files (`scripts/ops/pr_impact_gate.py`,
  `scripts/ops/select_tests.py`, `tests/ops/test_pr_impact_gate.py`,
  `tests/ops/test_select_tests.py`, and this campaign pair), zero deletions.
- Exact-head workflows: five runs completed successfully (Pytest
  `31481085768`, Pyright `31481085735`, Ruff `31481085733`, Bandit
  `31481085751`, Wiki `31481085790`).
- Protected exact-head run `31481084538` at the exact head: trusted
  controller PASS (48s), unprivileged executor PASS (34s), trusted verifier
  PASS (21s); impact run `31481085768` emitted `EXACT_BASELINE_DEBT` with
  `blocking=false`, `new_failures=[]`, `resolved_failures=[]`.
- Owner receipts: `DESIGN_REVIEW_ACCEPTED_WITH_CLAIM_CEILING`,
  `ISSUE_75_MONOTONIC_TEST_INVENTORY_CANDIDATE`, and
  `ISSUE_75_EXACT_HEAD_ACCEPTANCE_PASS` recorded on Issue #75; Issue #75 is
  closed `completed`.
- Reconciled current main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`;
  readback confirms `scripts/ops/pr_impact_gate.py` and
  `tests/ops/test_pr_impact_gate.py` are present and PR #118's merge is an
  ancestor of current main.

`EXACT_GIT_DELETION_PROVENANCE_PROVEN` proves only the exact GitHub
collaboration deletion-provenance foundation at its merged head. It grants no
#104/#105/#106, protected-ruleset/App enforcement, runtime, route, Workforce,
lifecycle, approval, integration, merge, release, or production authority.
`AUTO_CHAIN=false`.
