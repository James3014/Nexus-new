---
artifact_authority: current
owner: James Chen
status: active
purpose: Govern the Issue #104 no-checkout trusted-source repair.
---

# GitHub Issue #104 — No-checkout trusted-source repair

- Lifecycle task id: `github-issue-104-no-checkout-trusted-source-20260811`
- GitHub authority: Issue #104 and CONTRACT_DELTA comment
  `https://github.com/James3014/Nexus-new/issues/104#issuecomment-5248969210`
- Baseline: `main=fdb23157f4c8a78bd43dfc3cde7165a5c62b1bac`
- Frontier: `01-no-checkout-trusted-source.md`
- AUTO_CHAIN: `false`

The previous card
`tasks/github-issue-104-gitlink-checkout-repair-20260811/01-gitlink-safe-checkout-teardown.md`
is superseded because its post-checkout metadata step cannot prevent the failure
inside the main `actions/checkout` credential-removal phase.
