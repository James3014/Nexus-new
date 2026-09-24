# Issue #973 — governed one-shot Runtime Recovery

```yaml
campaign_id: github-issue-973-runtime-recovery-governed-20260923
repository: James3014/Nexus-new
issue: 973
status: READY_AFTER_TRACKING
execution_lane: GOVERNED
auto_chain: false
parallel_execution: false
current_frontier: 06-effect-continuity-cross-attempt-fence-r6.md
claim_ceiling: SOURCE_CANDIDATE_AND_INDEPENDENT_ACCEPTANCE_ONLY_NO_RUNTIME_ACTIVATION
source_mode: APPROVED_ISSUE_CONTRACT_PLUS_OWNER_GOVERNED_DECISION
source_issue_body_sha256: 4af2812fb7c84aec5d73ee74d9e74a4881a1d9a949b2e59602b6d211d6048b2f
owner_governed_decision_sha256: 5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5
bootstrap_standing_grant_receipt_sha256: 00d766ce52dfac3a85a6fdc8d6ac9b222f6aee2c4432424b7639c0b00d02487d
latest_contract_delta_basis_sha256: a9da77c251db97f7946664df9d59271670d94ea3c8dc1ff52dfebd6ffe2886e2
```

## Source and decision basis

- Canonical product/engineering contract: GitHub Issue #973, body SHA-256
  `4af2812fb7c84aec5d73ee74d9e74a4881a1d9a949b2e59602b6d211d6048b2f`.
- Explicit Owner decision in the active coordination thread:
  `#973 改走 GOVERNED，繼續完成。`, UTF-8 SHA-256
  `5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5`.
- Original governed bootstrap main: `2619f9f9121448b81bed8fe84556186892849e76`.
- Current R6 tracking base: `bc52b5da50ddc16e55018a624c751ffc0e70f864`.
- Prior direct Candidate `fbf6c00c7f1912846ccab843bdd9d534b9f19c19`, governed Candidate
  `3d88a614c27e0c21a15c68dc70dc3d2193084cee`, and PR #1098 head
  `cf3547d6056cd0aea1b1641f43cf0569269026af` are historical donor/evidence only.
  None is current acceptance or merge authority after the R6 contract delta.

### Original High obligations preserved

1. effect-commit freshness must use a fresh time immediately before durable `DISPATCHED`,
   after current revocation readback;
2. outer runtime transition self-hashes cannot certify terminal success; semantic tamper and
   terminal truth must be checked against the trusted Gateway reconcile/readback path.

### R6 contract delta

Source basis:
- #973 comment `5812072505` — PRE_EFFECT_AUTHORITY vs EFFECT_CONTINUITY refinement;
- #973 comment `5814508223` — static falsification of missing cross-attempt exclusion;
- combined immutable basis SHA-256:
  `a9da77c251db97f7946664df9d59271670d94ea3c8dc1ff52dfebd6ffe2886e2`.

New invariant:

> a fresh successor attempt must fail closed while any earlier #973 attempt is durably
> effect-committed and lacks trusted terminal closure.

The repair must not rewrite the fixed Gateway runtime manager or create another authority owner.

## Frontier

| Order | Card | Status | Observable exit |
|---|---|---|---|
| 1 | `00-runtime-recovery-one-shot-consumer.md` | HISTORICAL / SUPERSEDED_FOR_NEW_EXECUTION | original governed implementation contract; donor lineage only |
| 2 | `05-external-candidate-adoption-bridge-r5.md` | SUPERSEDED_FOR_NEW_EXECUTION | old immutable Candidate adoption may not be reused after material contract delta |
| 3 | `06-effect-continuity-cross-attempt-fence-r6.md` | ACTIVE_AFTER_TRACKING | new repaired Candidate independently accepted; no live runtime activation |

The R6 Card becomes governed mutation authority only after these exact INDEX/Card bytes are
tracked on canonical `main`. Any material R6 scope, acceptance, authority, or allowed-path
change requires a new bounded contract delta before mutation.

Tracking this Card does not execute it, approve a Candidate, merge implementation, activate
runtime recovery, release, or make production/public-readiness claims.

`AUTO_CHAIN=false`.
