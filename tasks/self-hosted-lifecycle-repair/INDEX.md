# Campaign Index: Self-hosted Lifecycle Repair

artifact_authority: current
owner: James Chen
status: active
source_revision: 1425848c7f5e720275bd635ba294f0006a901d51
AUTO_CHAIN: false

## Campaign Overview
Self-hosted Lifecycle 核心硬化與 recovery 能力收斂專案。修復範圍只限 Self-hosted Lifecycle，不涉及 GitHub Actions。

## Ordered Cards
1. [00-self-hosted-lifecycle-repair-authority-bootstrap.md](00-self-hosted-lifecycle-repair-authority-bootstrap.md) - `self-hosted-lifecycle-repair-authority-bootstrap`
2. [01-self-hosted-lifecycle-core-hardening.md](01-self-hosted-lifecycle-core-hardening.md) - `self-hosted-lifecycle-core-hardening`
3. [02-self-hosted-lifecycle-recovery-surfaces.md](02-self-hosted-lifecycle-recovery-surfaces.md) - `self-hosted-lifecycle-recovery-surfaces`

## Current Frontier
`self-hosted-lifecycle-repair-authority-bootstrap`

## Completed Cards
None

## Blocked Cards
- `self-hosted-lifecycle-core-hardening`: Task 01 blocked by Task 00 integration
- `self-hosted-lifecycle-recovery-surfaces`: Task 02 blocked by Task 01 integration

## Superseded Cards
None

## Task Dependencies
- `self-hosted-lifecycle-repair-authority-bootstrap`: None (bootstrap)
- `self-hosted-lifecycle-core-hardening`: Requires Task 00 integrated (`self-hosted-lifecycle-repair-authority-bootstrap`)
- `self-hosted-lifecycle-recovery-surfaces`: Requires Task 01 integrated (`self-hosted-lifecycle-core-hardening`)
