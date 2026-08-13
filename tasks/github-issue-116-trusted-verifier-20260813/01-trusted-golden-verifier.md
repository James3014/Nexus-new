---
artifact_authority: current
owner: James Chen
status: active
objective: Make the required default-branch verifier independently validate the exact PR-head Golden corpus and reject invalid or fake same-name evidence.
allowed_files:
  - .github/workflows/trusted-deletion-anchor.yml
  - scripts/ops/trusted_golden_verifier.py
  - tests/ops/test_trusted_golden_verifier.py
  - tasks/github-issue-116-trusted-verifier-20260813/INDEX.md
  - tasks/github-issue-116-trusted-verifier-20260813/01-trusted-golden-verifier.md
forbidden_scope:
  - main, rulesets, branch protection
  - trusted deletion controller/verifier semantics except additive Golden step
  - production runtime and lifecycle state
  - #191 and #143
verification:
  - python3 -m pytest -q tests/ops/test_trusted_golden_verifier.py
  - ruff check scripts/ops/trusted_golden_verifier.py tests/ops/test_trusted_golden_verifier.py
  - git diff --check
exit_criteria: Default-branch workflow invokes the hash-bound verifier against exact PR head; focused hostile tests prove invalid corpus and untrusted same-name evidence fail while exact valid corpus passes.
block_class: RECOVERABLE_BLOCK
claim_ceiling: Merge-gate evidence only; no approval, integration, release, or production claim.
---

# Trusted Golden verifier

The verifier reads the exact PR-head corpus from a fetched commit using
`git show` and parses it with `ast`; it never imports PR code or consumes a PR
workflow's success as authority. The workflow source and verifier source are
both acquired from the default branch by the existing trusted verifier job.
