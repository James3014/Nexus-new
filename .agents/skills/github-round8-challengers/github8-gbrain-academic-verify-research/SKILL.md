---
name: github8-gbrain-academic-verify-research
description: Prompt-only research challenger derived from GBrain academic-verify. Use for research/source-discipline comparisons requiring claim-to-publication-to-method-to-data traceability.
source_repo: https://github.com/garrytan/gbrain
source_commit: 1d5f69fe7afb26222e69674bed08d200a3f7f0a3
source_skill: skills/academic-verify/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# GBrain Academic Verify Research

Use only as a Nexus SF challenger for `research`. Convert academic verification into a receipt-friendly source discipline workflow.

## Boundaries

- Do not invoke Perplexity, external APIs, browser tools, or private brain storage.
- Do not treat unsupported claims as verified.

## Method

1. Extract the research claim and its expected evidence class.
2. Trace claim -> publication/source -> method -> data/artifact -> independent corroboration where available.
3. Mark unsupported or single-source claims as tentative.
4. Prefer source conflict detection over smooth synthesis.
5. Emit source chain, confidence, blockers, and outcome contribution.
