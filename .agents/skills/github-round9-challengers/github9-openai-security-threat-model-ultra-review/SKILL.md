---
name: github9-openai-security-threat-model-ultra-review
description: Prompt-only Ultra Review challenger derived from OpenAI curated security-threat-model. Use for repository-grounded trust boundaries, assets, abuse paths, mitigations, and security review; do not pause for user clarification during SF probes.
source_repo: https://github.com/openai/skills
source_commit: 590b49edc158611a2b2ed715ae73f27eb70d251a
source_skill: skills/.curated/security-threat-model/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# OpenAI Security Threat Model Ultra Review

Use only as a Nexus SF challenger for `ultra_review`. Adapt repository-grounded threat modeling into a fail-closed review receipt.

## Boundaries

- Do not ask clarifying questions during automated SF probes; record assumptions instead.
- Do not replace Nexus policy, claim, or delivery gates.

## Method

1. Scope the component, entry points, assets, and trust boundaries from available evidence.
2. Separate runtime behavior from CI/dev/test surfaces.
3. Enumerate realistic abuse paths tied to assets and boundaries.
4. Prioritize by likelihood, impact, existing controls, and residual risk.
5. Emit blocker status, mitigation focus, evidence refs, and outcome contribution.
