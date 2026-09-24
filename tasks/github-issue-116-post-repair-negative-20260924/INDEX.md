---
artifact_authority: current
owner: James Chen
status: active
purpose: Issue #116 post-repair controlled negative witness for the trusted default-branch Golden verifier path.
authority: Owner standing coordinator grant; evidence-only Draft PR; DO NOT MERGE.
repository: James3014/Nexus-new
base: c8da43aaab92dbd5d11734aeb15d6ee5dc23931d
claim_ceiling: TRUSTED DEFAULT-BRANCH EVALUATOR SEALED EXACT-HEAD CANONICAL GOLDEN EVIDENCE NEGATIVE RECEIPT ONLY
---

# Issue #116 — post-repair hostile negative witness

PR #229 merged the trusted default-branch Golden verifier. Issue #116 remains
open pending one post-repair controlled negative receipt proving that
branch-controlled same-name substitution cannot satisfy the newly merged
Trusted verifier path. This campaign produces that receipt.

This branch intentionally (a) makes the Golden corpus validator fail through one
reversible duplicate `case_id`, (b) suppresses the real `Exact-base impact gate`
on this exact branch, and (c) emits untrusted same-name SUCCESS checks for both
the `Exact-base impact gate` and `Trusted verifier (default branch)` contexts.
It is evidence-only and must never merge.

Active card: `01-controlled-negative-test.md`.

Forbidden: ruleset/branch-protection mutation, Trusted verifier workflow
mutation, `main` mutation, merge, force-push, issue closure, lifecycle approval,
release/production claims, #191, #143, and PR #228 mutation.