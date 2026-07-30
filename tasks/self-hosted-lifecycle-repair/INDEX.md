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
`self-hosted-lifecycle-recovery-surfaces`

## Completed Cards
- `self-hosted-lifecycle-repair-authority-bootstrap`: status=INTEGRATED, candidate_commit=628290120d709cab6865e04c6c3d09c23c853138, integration_commit=007b536be121573622b55e2b5e65b3cf7e1506b9
- `self-hosted-lifecycle-core-hardening`: status=INTEGRATED, candidate_commit=c369288c485c7238412f35a25d7caa76713679bf, candidate_tree=d3b867980074fc969069739c270b8ef6dad03345, integration_commit=a99c71d8c0628e1d383adaf3a905cad2c6b1b7f4

## Ready Cards
- `self-hosted-lifecycle-recovery-surfaces`: Task 01 integrated (`self-hosted-lifecycle-core-hardening`), dependencies satisfied

## Blocked Cards
None

## Superseded Cards
None

## Task Dependencies
- `self-hosted-lifecycle-repair-authority-bootstrap`: None (bootstrap)
- `self-hosted-lifecycle-core-hardening`: Requires Task 00 integrated (`self-hosted-lifecycle-repair-authority-bootstrap`)
- `self-hosted-lifecycle-recovery-surfaces`: Requires Task 01 integrated (`self-hosted-lifecycle-core-hardening`)
