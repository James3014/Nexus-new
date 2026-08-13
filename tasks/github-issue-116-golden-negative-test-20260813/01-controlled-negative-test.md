---
artifact_authority: current
owner: James Chen
status: active
objective: Prove the existing Golden Behavior validator fails closed on a deterministic corpus defect.
allowed_files:
  - tests/golden_behavior/corpus.py
  - tasks/github-issue-116-golden-negative-test-20260813/INDEX.md
  - tasks/github-issue-116-golden-negative-test-20260813/01-controlled-negative-test.md
forbidden_scope:
  - production source
  - .github/workflows
  - rulesets or branch protection
  - main, merge, force-push, issue closure
  - #191 and #143
verification:
  - .venv/bin/python scripts/ops/run_golden_behavior_eval.py --validate-only
  - git diff --check
exit_criteria: Expected validator failure captured; exact base/head, changed files, app/check context, PR state, and ruleset readback recorded in PR/receipt.
block_class: RECOVERABLE_BLOCK
claim_ceiling: Evidence-only negative test; no enforcement, approval, integration, release, or production claim.
---

# Controlled negative test

The single corpus edit changes `GB-083` to duplicate `GB-082` while keeping
Python syntax valid. `run_golden_behavior_eval.py --validate-only` must return
exit code 2 with `duplicate_case_id`; this is an expected failure, not a
product regression.

The resulting PR is Draft and explicitly marked **DO NOT MERGE**. Restore the
corpus edit only in a later Owner-approved cleanup; this card does not merge or
delete the branch.
