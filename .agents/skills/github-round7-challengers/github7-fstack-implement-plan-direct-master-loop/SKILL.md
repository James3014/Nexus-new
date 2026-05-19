---
name: github7-fstack-implement-plan-direct-master-loop
description: Prompt-only direct execution challenger derived from fstack implement-plan. Use for direct master loop comparisons only.
source_repo: https://github.com/fredrick84823/fstack
source_commit: 3be8ef349c9ca61c25fc0efb9fab6f03c908f617
source_skill: skills/implement-plan
runtime_mount_candidate: false
sf_challenger_only: true
---

# FStack Implement Plan Direct Master Loop

Use this skill only as a Nexus SF challenger for `direct_master_loop`. It turns an approved plan into phased execution while preserving Nexus fail-closed gates.

## Boundaries

- Do not pause for manual confirmation during automated SF probes.
- Do not modify runtime policy or catalog directly.
- Do not bypass tests, receipts, or hidden verifier results.

## Method

1. Convert the task into short ordered phases with a single current phase.
2. For each phase, identify the smallest file or behavior slice that proves progress.
3. Execute only the slice needed for the current phase.
4. Verify with the most local available evidence before moving forward.
5. If verification fails, classify the failure and repair the phase before expanding scope.
6. Report completion with changed surface, verification evidence, and residual blockers.
