# Issue #973 — governed one-shot Runtime Recovery

```yaml
campaign_id: github-issue-973-runtime-recovery-governed-20260923
repository: James3014/Nexus-new
issue: 973
status: READY_AFTER_TRACKING
execution_lane: GOVERNED
auto_chain: false
parallel_execution: false
current_frontier: 00-runtime-recovery-one-shot-consumer.md
claim_ceiling: SOURCE_CANDIDATE_AND_INDEPENDENT_ACCEPTANCE_ONLY_NO_RUNTIME_ACTIVATION
source_mode: APPROVED_ISSUE_CONTRACT_PLUS_OWNER_GOVERNED_DECISION
source_issue_body_sha256: 4af2812fb7c84aec5d73ee74d9e74a4881a1d9a949b2e59602b6d211d6048b2f
owner_governed_decision_sha256: 5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5
bootstrap_standing_grant_receipt_sha256: 00d766ce52dfac3a85a6fdc8d6ac9b222f6aee2c4432424b7639c0b00d02487d
```

## Source and decision basis

- Canonical product/engineering contract: GitHub Issue #973, body SHA-256
  `4af2812fb7c84aec5d73ee74d9e74a4881a1d9a949b2e59602b6d211d6048b2f`.
- Explicit Owner decision in the active coordination thread:
  `#973 改走 GOVERNED，繼續完成。`, UTF-8 SHA-256
  `5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5`.
- Canonical starting main: `2619f9f9121448b81bed8fe84556186892849e76`, tree
  `76bdd05e94e2a1ba01f5364605f2e42ea922822a`.
- Prior direct Candidate `fbf6c00c7f1912846ccab843bdd9d534b9f19c19` is evidence/donor only;
  it is **not** governed mutation authority and must not be merged or treated as accepted.
- Independent read-only review of that prior Candidate identified two High repair obligations
  that this governed attempt must close before acceptance:
  1. effect-commit freshness must use a fresh time immediately before durable `DISPATCHED`,
     not a stale caller timestamp captured before remote revocation readback;
  2. runtime transition inspection/reconciliation must reject semantic terminal/dispatch
     tampering even when a same-UID process rewrites fields and recomputes self-hashes.

## Frontier

| Order | Card | Status | Observable exit |
|---|---|---|---|
| 1 | `00-runtime-recovery-one-shot-consumer.md` | READY_AFTER_TRACKING | exact governed Candidate independently accepted and source-integrated; no live runtime activation |

This campaign becomes executable only after these exact INDEX/Card bytes are tracked on
canonical `main`. Any material card, Issue-contract, or allowed-scope change requires an
explicit bounded contract delta before mutation.

`AUTO_CHAIN=false`.
