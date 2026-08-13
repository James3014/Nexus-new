# Issue #8 — GitHub orchestration intent (M4)

- authority: Owner-authorized Ready GitHub Issue #8; fresh remote `main`
- historical baseline: `a74d838cc6bb14af47ce79207181c12a1aed1d35`
- reconciled/current main: `eb668fb76f0c30d8f025db42cdb8e320d556c037`
- status: COMPLETE
- frontier status: COMPLETE
- current frontier: terminal reconciliation; `00-github-orchestration-intent.md` completed
- AUTO_CHAIN: false
- terminal marker: `NEXUS_GITHUB_ORCHESTRATION_M4_INTENT_SUBSTRATE_VERIFIED`
- physical receipt: PR #234, head `87998b0e1c555170b91062e902d6a9c5aae36a21`,
  merge `8e0986b40db56016c79b03eb81ff3d03c85c6f32`; exact-main verification
  references include 140 focused tests/checks.
- claim ceiling: `NEXUS_GITHUB_ORCHESTRATION_M4_INTENT_ONLY`; deterministic
  orchestration-intent substrate projection only. No adapter, network,
  subprocess, merge executor, runtime, provider, approval, integration,
  production, or protected-main truth.
- dependencies: Issue #17 remains a separate downstream authority and is not
  activated by this terminal reconciliation.

This campaign closes at the verified metadata/intent substrate. The receipt
does not authorize GitHub mutation or any later merge, runtime, or production
action.
