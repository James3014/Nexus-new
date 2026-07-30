# Campaign Index: Self-hosted Operator Workflow

artifact_authority: current
owner: James Chen
status: active
AUTO_CHAIN: false

## Campaign Overview
降低Self-hosted operator人工shell操作，但不降低Candidate、approval或integration治理強度。

## Ordered Cards
1. [00-self-hosted-verification-entrypoint.md](00-self-hosted-verification-entrypoint.md) - `self-hosted-verification-entrypoint`
2. [00a-self-hosted-verification-entrypoint-final-amendment.md](00a-self-hosted-verification-entrypoint-final-amendment.md) - `self-hosted-verification-entrypoint-final-amendment`
3. [00b-self-hosted-verification-entrypoint-opencode-recovery.md](00b-self-hosted-verification-entrypoint-opencode-recovery.md) - `self-hosted-verification-entrypoint-opencode-recovery`

## Current Frontier
`self-hosted-verification-entrypoint-opencode-recovery`

## Completed Cards
None

## Ready Cards
- `self-hosted-verification-entrypoint-opencode-recovery`: READY; clean seven-file reconstruction using the rejected Candidate and Codex salvage as read-only evidence

## Blocked Cards
- `self-hosted-verification-entrypoint`: NEEDS_AMENDMENT; physical Candidate `a2d8e764464a2a0bf3b1fac21f612cc9998a9354` is not approved for integration
- `self-hosted-verification-entrypoint-final-amendment`: RECOVERABLE_BLOCK; Codex exited 1 after 650833 ms and produced only non-candidate salvage `29b9b0d40eb29e0ea590d4cbf05118c7ba3ae43d`

## Superseded Cards
None

## Task Dependencies
- `self-hosted-verification-entrypoint`: None (bootstrap)
- `self-hosted-verification-entrypoint-final-amendment`: blocked by Codex execution failure; superseded for execution by `self-hosted-verification-entrypoint-opencode-recovery`
- `self-hosted-verification-entrypoint-opencode-recovery`: depends on the original review findings and durable Codex salvage; must reconstruct the complete seven-file feature from a clean base
