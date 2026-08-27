# TASK-G4-659-01 — Continuous published-history secret enforcement

## Authority / status

- Source: GitHub Issue #659 plus Owner instruction `完成g4`.
- Status: `ACTIVE`.
- Execution domain: governed GitHub collaboration.
- Baseline: `45d39c6ca7940ac42752d2c6e5bba41bf6b968da`.
- `AUTO_CHAIN=false`.
- Maximum implementation claim: `G4_CONTINUOUS_SECRET_ENFORCEMENT_CANDIDATE_ONLY`.

## Objective

Turn the existing G2 full published-history secret audit into a continuous fail-closed repository guard by adding unconditional PR-to-main, push-to-main, periodic schedule, and manual triggers, while preserving the existing scanner, exact-head/ref coverage, redaction, immutable Action refs, and least-privilege permissions.

## Allowed files

1. `.github/workflows/git-history-secret-audit.yml`
2. `tests/ops/test_git_history_secret_scan.py`
3. `tasks/github-issue-g4-continuous-secret-enforcement-20260828/00-g4-continuous-secret-enforcement.md`
4. `tasks/github-issue-g4-continuous-secret-enforcement-20260828/INDEX.md`

No deletions.

## Forbidden scope

No scanner redesign; no secret rotation/revocation; no history rewrite, force-push, branch/ref deletion, unrelated workflow/security-policy change, runtime activation, release, or production claim. The worker cannot mutate branch protection/rulesets, approve, merge, or close the Issue.

## Required implementation

- `pull_request` targets `main` with no path filter.
- `push` targets `main`.
- a periodic `schedule` is present.
- `workflow_dispatch` remains present.
- `permissions: contents: read` remains unchanged.
- external Actions remain pinned to immutable 40-hex commit SHAs.
- existing full-ref fetch/convergence, checkout-credential removal, exact source/snapshot assertions, redacted receipt behavior, and artifact upload remain intact.
- focused tests statically prove the trigger, no-path-bypass, permission, and immutable-action-ref contract.

## Verifiers

- `pytest -q tests/ops/test_git_history_secret_scan.py`
- `python3 scripts/ops/git_history_secret_scan.py --repo . --output /tmp/g4-git-history-secret-scan.json`
- `git diff --check`

The scan receipt must be `PASS`, have `blocking_finding_count=0`, and `secret_values_emitted=false`.

## Candidate / acceptance

Implementation must be committed on the Issue branch and independently reviewed against this exact card, Issue #659, exact commit/tree/diff, and verifier evidence. Candidate acceptance, protected merge, post-merge audit observation, ruleset mutation, and Issue closure are coordinator-only subsequent gates under separately valid authority.

## Exit

Exit implementation only with exact scoped Candidate identity and all verifiers green, or with a bounded fail-closed block. Do not auto-chain.