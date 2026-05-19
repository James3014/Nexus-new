---
name: github8-claude-osint-research-control-plane
description: Prompt-only research control challenger derived from Claude-OSINT methodology. Use for authorized research/control-plane comparisons that need source hygiene, confidence levels, and evidence discipline; do not use for active exploitation or real-world recon.
source_repo: https://github.com/elementalsouls/Claude-OSINT
source_commit: ea42241d068e8112da0e4e28006207125c835c2e
source_skill: skills/osint-methodology/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# Claude OSINT Research Control Plane

Use only as a Nexus SF challenger for `research_control_plane`. Convert OSINT methodology into conservative source-planning and evidence-review behavior.

## Boundaries

- No active probing, exploitation, credential validation, rate-limit bypass, phishing, or target enumeration.
- Do not run external OSINT tools or browse third-party targets during SF tests.
- Treat all outputs as internal research-control receipts, not public claims.

## Method

1. Define the research target, authorization/scope boundary, and allowed evidence types.
2. Build a source plan with confidence levels: tentative, firm, confirmed.
3. Prefer corroborated source chains over single-source assertions.
4. Record each claim with evidence refs, timestamp expectation, and downgrade rule when corroboration is missing.
5. Return a compact research-control verdict with selected, used, evidence_present, gate_passed, and outcome_contributed fields when requested.
