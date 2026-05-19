---
name: github9-complexity-optimizer-codeintel
description: Prompt-only CodeIntel challenger derived from codex-complexity-optimizer. Use for complexity hotspot reasoning, safe optimization planning, and code impact analysis; do not run external scanner scripts unless explicitly invoked by Nexus.
source_repo: https://github.com/Kappaemme-git/codex-complexity-optimizer
source_commit: 6a1f9674d706a06d462296e53a40f668299e8893
source_skill: complexity-optimizer/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# Complexity Optimizer CodeIntel

Use only as a Nexus SF challenger for `codeintel`. Convert complexity hotspot analysis into code-intelligence receipts.

## Boundaries

- Do not run bundled scanner scripts or edit files during SF smoke.
- Treat static findings as leads, not proof.

## Method

1. Identify hot path, data shape, and behavior that must be preserved.
2. Look for repeated scans, nested loops, sort-in-loop, N+1 access, costly recomputation, and rendering churn.
3. Rank opportunities by impact, correctness risk, and testability.
4. Recommend the smallest behavior-preserving change and verification path.
5. Emit evidence refs, risk level, and outcome contribution for CodeIntel receipt.
