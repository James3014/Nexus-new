---
artifact_authority: current
owner: James Chen
status: active
purpose: Issue #116 trusted default-branch Golden verifier repair.
authority: Owner standing coordinator grant; issue branch and Draft PR only.
repository: James3014/Nexus-new
base: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
---

# Issue #116 — trusted default-branch Golden verifier

This campaign adds a default-branch-controlled, fail-closed verifier for the
exact pull-request head's Golden corpus. It is independent of same-name jobs
published by a PR branch. It does not mutate `main`, rulesets, branch
protection, or production behavior.

Active card: `01-trusted-golden-verifier.md`.

Forbidden: merge, force-push, ruleset/settings mutation, issue closure,
lifecycle approval, release/production claims, #191, and #143.
