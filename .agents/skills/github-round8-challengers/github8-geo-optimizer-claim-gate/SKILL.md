---
name: github8-geo-optimizer-claim-gate
description: Prompt-only claim gate challenger derived from GEO Optimizer. Use for claim/citation readiness checks, factual sourcing, structured evidence, and AI-citability diagnostics; do not run the geo CLI or modify websites.
source_repo: https://github.com/Auriti-Labs/geo-optimizer-skill
source_commit: 650f3ed310489e8c8a255b2d7454f8935be503a4
source_skill: SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# GEO Optimizer Claim Gate

Use only as a Nexus SF challenger for `claim_gate`. Adapt GEO/citability checks into a prompt-only evidence and claim readiness gate.

## Boundaries

- Do not run `geo`, MCP tools, install scripts, crawlers, or website mutations.
- Do not claim public SEO/GEO improvement from SF smoke evidence.

## Method

1. Identify every factual claim, citation claim, and discoverability claim in the task output.
2. Check whether claims are supported by durable evidence, clear source naming, concrete dates/numbers, and structured context.
3. Flag missing citation, stale content, ungrounded statistics, hidden instruction risk, and negative citation signals.
4. Separate delivery PASS from claim-ready PASS.
5. Emit claim gate status, blocker reasons, evidence refs, and outcome contribution.
