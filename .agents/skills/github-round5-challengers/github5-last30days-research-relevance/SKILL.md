---
name: github5-last30days-research-relevance
description: "Use for research_control_plane work that needs recent-source discovery, freshness checks, source mix planning, and evidence-backed source triage. This prompt-only SF challenger is adapted from mvanhorn/last30days-skill; do not use for live web scraping, API access, external network calls, runtime default changes, or public benchmark claims."
metadata: {"source_repo":"https://github.com/mvanhorn/last30days-skill","source_commit":"850c7e01857bd1b429b902af53d8dc60c6815f4e","source_path":"skills/last30days/SKILL.md","source_status":"generated_prompt_only_candidate","runtime_eligible":true,"ablation_eligible":true}
---

# GitHub Round5 Last30Days Research Relevance Candidate

## Load when
- Nexus is running an internal SF ablation for `research_control_plane`.
- The task needs source freshness, recency windows, trend validation, or source mix planning.
- The expected output is a research plan or source discipline receipt, not live scraping.

## Do not load when
- The task requires direct network calls, scraping, API credentials, browser automation, or social platform access.
- The result would be used as public research evidence without a separate source-verification gate.
- The workflow attempts to change runtime policy or skill defaults.

## Operating contract
- Stay prompt-only and plan evidence collection without executing it.
- Separate recent-source discovery, source credibility, and claim validation.
- Produce explicit receipt requirements for every proposed source.
- Fail closed if source freshness or evidence paths cannot be verified.

## Required receipt fields
- `selected`
- `injected`
- `used`
- `evidence_present`
- `gate_passed`
- `outcome_contributed`

## Output shape
Return:

1. Recency window and source classes.
2. Candidate source queue.
3. Credibility and freshness checks.
4. Claim-to-source mapping.
5. Evidence paths required before promotion.

