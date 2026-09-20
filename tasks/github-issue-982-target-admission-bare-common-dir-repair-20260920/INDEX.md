# Campaign Index: github-issue-982-target-admission-bare-common-dir-repair-20260920

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Repair the target-admission reservation lock so a controller checkout whose `git rev-parse --git-common-dir` resolves to a valid bare/common Git directory such as `repository.git` is accepted. Remove the basename==`.git` assumption while preserving fail-closed controller toplevel identity, existence/directory validation, Git-owned common-dir provenance, flock serialization, and all existing target/lease boundaries. Add regression tests that reproduce the gateway-direct deployment shape and negative controls for invalid/non-directory common-dir evidence. No route, Workforce, Task Card, provider, merge, release, or canary semantics change.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-982-target-admission-bare-common-dir-repair-20260920` | `00-issue-982-target-admission-bare-common-dir-repair-20260920.md` | ACTIVE | Owner confirmation |
