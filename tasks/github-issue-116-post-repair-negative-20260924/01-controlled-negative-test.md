---
artifact_authority: current
owner: James Chen
status: active
objective: Prove the repaired default-branch Trusted verifier fails closed on a deterministic corpus defect and that untrusted same-name branch checks cannot substitute for the required `Trusted verifier (default branch)` context.
allowed_files:
  - tests/golden_behavior/corpus.py
  - .github/workflows/pytest.yml
  - tasks/github-issue-116-post-repair-negative-20260924/INDEX.md
  - tasks/github-issue-116-post-repair-negative-20260924/01-controlled-negative-test.md
forbidden_scope:
  - production source
  - rulesets or branch protection
  - .github/workflows/trusted-deletion-anchor.yml or its scripts
  - main, merge, force-push, issue closure
  - PR #228 mutation
  - #191 and #143
verification:
  - .venv/bin/python scripts/ops/run_golden_behavior_eval.py --validate-only
  - git diff --check
  - YAML parse for .github/workflows/pytest.yml
exit_criteria: Expected real Trusted verifier failure captured; exact base/head, changed files, check context identity, PR mergeStateStatus, and ruleset readback recorded; classification NOT_REPRODUCIBLE (repair holds) or SAME_APP_SAME_NAME_BYPASS_REPRODUCIBLE_2 (defect) determined from readback truth.
block_class: RECOVERABLE_BLOCK
claim_ceiling: Evidence-only negative receipt; no enforcement, approval, integration, release, or production claim.
---

# Post-repair controlled negative test

The corpus edit changes `GB-083` to duplicate `GB-082` while keeping Python
syntax valid. `run_golden_behavior_eval.py --validate-only` must return exit
code 2 with `duplicate_case_id`; this is an expected failure, not a product
regression.

The resulting PR is Draft and explicitly marked **DO NOT MERGE**. Restore the
corpus edit only in a later Owner-approved cleanup; this card does not merge or
delete the branch.

## Phase 2 — post-repair same-name substitution against the trusted path

On this branch only, the real `impact-gate` job is excluded by its exact branch
name. Two separate jobs emit passing checks with the protected context names:

- `Exact-base impact gate`
- `Trusted verifier (default branch)`

Neither substitutes a checkout, Golden evaluator run, or trusted verifier
source. The real default-branch Trusted verifier (build from `pull_request_target`
against the exact PR head) must independently FAIL this branch because of the
duplicate `case_id`. This is deliberately untrusted evidence.

Capture the exact head, the real and fake same-name check records (each with
workflow/run identity), ruleset readback, and PR `mergeStateStatus` after all
checks settle.

- Classify `NOT_REPRODUCIBLE` (repair holds) if the invalid corpus PR stays
  `BLOCKED`/unmergeable even though a same-name SUCCESS check with the trusted
  context name exists on the head commit.
- Classify `SAME_APP_SAME_NAME_BYPASS_REPRODUCIBLE_2` if GitHub accepts the
  untrusted same-name check and reports the PR mergeable/`CLEAN`.

Either result is recorded truthfully on Issue #116; only `NOT_REPRODUCIBLE`
supports closing the Issue.