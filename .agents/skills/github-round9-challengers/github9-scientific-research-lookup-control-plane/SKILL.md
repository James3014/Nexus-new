---
name: github9-scientific-research-lookup-control-plane
description: Prompt-only research-control challenger derived from K-Dense research-lookup. Use for current scientific information routing, source prioritization, and research backend decision discipline; do not invoke parallel-cli, APIs, Perplexity, or OpenRouter.
source_repo: https://github.com/K-Dense-AI/scientific-agent-skills
source_commit: 044285c33a78afda10468012105b86a225f66267
source_skill: scientific-skills/research-lookup/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# Scientific Research Lookup Control Plane

Use only as a Nexus SF challenger for `research_control_plane`. Adapt scientific lookup routing into prompt-only source planning.

## Boundaries

- Do not call parallel-cli, API backends, OpenRouter, Perplexity, or external search tools.
- Do not claim current-source verification unless Nexus evidence refs exist.

## Method

1. Classify the query: general research, academic paper lookup, deep synthesis, or technical reference.
2. Define the preferred source class and why it fits the claim.
3. Prioritize academic and primary sources for scientific claims.
4. Mark backend choice as a planned route only, not executed evidence.
5. Emit route decision, source discipline, evidence gap, and outcome contribution.
