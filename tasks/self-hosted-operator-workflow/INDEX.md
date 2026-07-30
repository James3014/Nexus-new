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
3. [00c-self-hosted-retained-target-auto-closeout.md](00c-self-hosted-retained-target-auto-closeout.md) - `self-hosted-retained-target-auto-closeout`
4. [00b-self-hosted-verification-entrypoint-opencode-recovery.md](00b-self-hosted-verification-entrypoint-opencode-recovery.md) - `self-hosted-verification-entrypoint-opencode-recovery`

## Current Frontier
`self-hosted-verification-entrypoint-opencode-recovery`

## Completed Cards
- `self-hosted-retained-target-auto-closeout`: INTEGRATED at `17cf433ef218ea709d2e06ac1d3fcd2e85b90144`; retained Targets can now be salvaged/protected and released without promotion

## Ready Cards
- `self-hosted-verification-entrypoint-opencode-recovery`: READY; clean seven-file reconstruction using the rejected Candidate and Codex salvage as read-only evidence

## Blocked Cards
- `self-hosted-verification-entrypoint`: NEEDS_AMENDMENT; physical Candidate `a2d8e764464a2a0bf3b1fac21f612cc9998a9354` is not approved for integration
- `self-hosted-verification-entrypoint-final-amendment`: RECOVERABLE_BLOCK; Codex exited 1 after 650833 ms and produced only non-candidate salvage `29b9b0d40eb29e0ea590d4cbf05118c7ba3ae43d`

## Superseded Cards
- `self-hosted-terminal-auto-closeout`: unexecuted OpenCode draft; historical evidence only, superseded by integrated `self-hosted-retained-target-auto-closeout`

## Task Dependencies
- `self-hosted-verification-entrypoint`: None (bootstrap)
- `self-hosted-verification-entrypoint-final-amendment`: blocked by Codex execution failure; superseded for execution by `self-hosted-verification-entrypoint-opencode-recovery`
- `self-hosted-retained-target-auto-closeout`: depends on the reproduced cleanup lifecycle defect and existing salvage primitives
- `self-hosted-verification-entrypoint-opencode-recovery`: depends on integrated `self-hosted-retained-target-auto-closeout`, then the original review findings and durable Codex salvage; must reconstruct the complete seven-file feature from a clean base
