---
artifact_authority: current
owner: James Chen
status: active
purpose: Issue #116 trusted default-branch Golden verifier repair.
authority: Owner standing coordinator grant; issue branch and Draft PR only.
repository: James3014/Nexus-new
base: eb668fb76f0c30d8f025db42cdb8e320d556c037
repair_from_head: 2654dd58fa606f7e36271b66a77b71923f5e234a
max_files: 8
authorized_deletions: []
AUTO_CHAIN: false
claim_ceiling: TRUSTED_DEFAULT_BRANCH_EVALUATOR_SEALED_EXACT_HEAD_CANONICAL_GOLDEN_EVIDENCE_CANDIDATE_ONLY
---

# Issue #116 — trusted default-branch Golden verifier

This campaign adds a default-branch-controlled, fail-closed verifier for the
exact pull-request head's Golden corpus. It is independent of same-name jobs
published by a PR branch. It does not mutate `main`, rulesets, branch
protection, or production behavior.

Active card: `01-trusted-golden-verifier.md`.

Owner-authorized scope rebind: the repair uses exactly eight files. It adds
`scripts/ops/trusted_deletion_anchor.py` to the original verifier scope and
adds `scripts/ops/run_golden_behavior_eval.py` only for a trusted explicit,
SHA-bound repository-root seam. The legacy evaluator invocation remains
unchanged. The existing workflow is already one of the eight allowed files and
continues to invoke only the anchor controller/executor/verifier subcommands;
no ninth file or second evaluator path is admitted.

Exact allowed files:

1. `.github/workflows/trusted-deletion-anchor.yml`
2. `scripts/ops/trusted_deletion_anchor.py`
3. `scripts/ops/trusted_golden_verifier.py`
4. `scripts/ops/run_golden_behavior_eval.py`
5. `tests/ops/test_trusted_deletion_anchor.py`
6. `tests/ops/test_trusted_golden_verifier.py`
7. `tasks/github-issue-116-trusted-verifier-20260813/INDEX.md`
8. `tasks/github-issue-116-trusted-verifier-20260813/01-trusted-golden-verifier.md`

Forbidden: fake or GB-only canonical fixtures, privileged execution of PR
evaluator code, weakened hashes or file modes, merge, force-push,
ruleset/settings mutation, issue closure, lifecycle approval,
release/production claims, PR #228 mutation, #191, and #143.
