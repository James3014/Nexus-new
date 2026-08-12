---
artifact_authority: current
owner: James Chen
status: active
purpose: Govern the bounded Issue #104 executor archive bootstrap repair.
---

# GitHub Issue #104 — executor archive bootstrap repair

- Lifecycle task id: `github-issue-104-executor-archive-bootstrap-20260811`
- Authority: Owner request for Issue #104 executor archive bootstrap seam
- Baseline: `main=6c8ad898ad52b5b7569cf3878b1b59c39bd5da0e`
- Protected run: `31466863912` (controller PASS)
- Frontier: `01-executor-archive-bootstrap.md`
- AUTO_CHAIN: `false`

The first new failure is unprivileged executor extraction of an archive with an
irrelevant absolute symlink under Python `tarfile` data filtering. This card is
limited to the extraction seam and its focused tests.
