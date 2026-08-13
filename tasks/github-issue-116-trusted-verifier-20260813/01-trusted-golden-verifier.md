---
artifact_authority: current
owner: James Chen
status: active
objective: Make the required default-branch verifier independently validate the exact PR-head Golden corpus and reject invalid or fake same-name evidence.
allowed_files:
  - .github/workflows/trusted-deletion-anchor.yml
  - scripts/ops/trusted_deletion_anchor.py
  - scripts/ops/trusted_golden_verifier.py
  - scripts/ops/run_golden_behavior_eval.py
  - tests/ops/test_trusted_deletion_anchor.py
  - tests/ops/test_trusted_golden_verifier.py
  - tasks/github-issue-116-trusted-verifier-20260813/INDEX.md
  - tasks/github-issue-116-trusted-verifier-20260813/01-trusted-golden-verifier.md
max_files: 8
authorized_deletions: []
AUTO_CHAIN: false
forbidden_scope:
  - main, rulesets, branch protection
  - trusted deletion controller/verifier semantics except the additive canonical Golden result binding authorized here
  - any fixture change beyond the mandatory trusted Golden blob fixture
  - fake, synthetic, GB-only, skipped, or partial evidence presented as canonical success
  - privileged execution of pull-request evaluator code
  - PR #228 mutation
  - production runtime and lifecycle state
  - #191 and #143
verification:
  - python3 -m pytest -q tests/ops/test_trusted_golden_verifier.py
  - python3 -m pytest -q tests/ops/test_trusted_deletion_anchor.py
  - ruff check scripts/ops/trusted_golden_verifier.py scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_golden_verifier.py tests/ops/test_trusted_deletion_anchor.py
  - git diff --check
exit_criteria: Default-branch workflow invokes the hash-bound verifier against exact PR head; focused hostile tests prove invalid corpus and untrusted same-name evidence fail while exact valid corpus passes; anchor fixture supplies the mandatory regular trusted Golden blob.
block_class: RECOVERABLE_BLOCK
claim_ceiling: TRUSTED_DEFAULT_BRANCH_EVALUATOR_SEALED_EXACT_HEAD_CANONICAL_GOLDEN_EVIDENCE_CANDIDATE_ONLY
---

# Trusted Golden verifier

The verifier consumes the canonical Golden evaluator result produced by the
existing unprivileged executor against the exact fetched PR head. The trusted
default-branch controller binds that result, the exact head, source tree,
evaluator identity, and evidence hashes into its sealed evidence bundle. A
partial AST reimplementation, minimum-count heuristic, or same-name PR job is
not equivalent authority.

Owner-authorized `FIXTURE_NON_EQUIVALENT` delta: the existing trusted-anchor
shell fixture must include `scripts/ops/trusted_golden_verifier.py` as a regular
blob so the acquisition tests model the newly mandatory trusted source. The
fixture must retain hostile-head, missing, malformed, non-regular, and
wrong-source fail-closed coverage.

Owner-authorized controller delta: `scripts/ops/trusted_deletion_anchor.py`
may change only to carry and verify the canonical Golden result in the existing
controller/executor evidence path. Evaluation remains unprivileged; the
trusted workflow validates the sealed binding but never executes PR code or a
duplicate evaluator in its privileged job.

Owner-authorized evaluator delta: `scripts/ops/run_golden_behavior_eval.py`
may add an explicit SHA-bound repository-root API/CLI used only by the trusted
anchor. It must validate the exact clean PR head/tree and canonical corpus/test
topology. Its legacy no-root invocation and report consumers remain backward
compatible. Evaluator bytes come from the trusted default-branch workflow SHA;
only the exact-head source and corpus are read from the unprivileged checkout.
