# Issue 955 — exact GitHub remote identity

Lane: GOVERNED GitHub integration of independently accepted DIRECT_DELEGATED source.
Owner: James3014. Coordinator: primary-codex-coordinator.
Goal: ISSUE-955-IDENTITY-REPAIR. AUTO_CHAIN=false.
Authority: current Owner request “合併並且更新github” in task 01a09040-6ed2-7c80-9b20-bed80b94a535; canonical receipt owner-issue-955-merge-20260911.
Issue: https://github.com/James3014/Nexus-new/issues/955
PR: https://github.com/James3014/Nexus-new/pull/954

## Frozen scope
- nexus/orchestrator/execution_readiness.py
- tests/nexus/orchestrator/test_execution_readiness.py
- tasks/github-issue-955-identity-20260911/00-identity.md
- tasks/github-issue-955-identity-20260911/INDEX.md

## Acceptance
Reject spoofed hosts, embedded GitHub path segments, malformed remotes and dot paths; preserve supported exact GitHub HTTPS/SSH forms and commit/tree gates. Luna source commit fddfaba3e is independently reviewed by primary; base 64bfb11aea2d6583cdf49d956992bd810a0c1cdc.
Run execution readiness unit and contract tests, Ruff lint and preview formatting, git diff --check, and applicable GitHub checks on the exact final head/base. Review scope, deletions and unresolved reviews before expected-head/CAS merge. Read back merged main and reconcile Issue 955.

## Claim ceiling
Source integration only. No runtime reload, deployment, release, production claim, #807 reopening or downstream dispatch. Worker cannot approve or merge. Missing checks, source drift or authority fails closed.
