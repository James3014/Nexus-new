---
artifact_authority: current
owner: James Chen
status: active
purpose: Issue #116 controlled negative Golden Behavior merge-gate test.
authority: Owner standing coordinator grant; evidence-only Draft PR; DO NOT MERGE.
repository: James3014/Nexus-new
base: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
---

# Issue #116 — controlled negative test

This campaign intentionally makes the existing Golden Behavior corpus
validator fail through one reversible duplicate `case_id`. It tests that a
failed/malformed Golden result is visible and cannot be treated as required
green evidence. This branch and Draft PR are evidence-only and must not merge.

Active card: `01-controlled-negative-test.md`.

Forbidden: production changes, workflow/ruleset changes, `main` mutation,
merge, force-push, issue closure, lifecycle approval, #191, and #143.
