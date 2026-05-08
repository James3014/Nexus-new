---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

## Context

Route cost tuning for public benchmark and repair tasks exposed two recurring over-selection failures:

1. Benchmark-injected `Nexus wearing contract` text leaked into runtime lexical signals and falsely enabled claim/evidence/governance-heavy capabilities.
2. Generic words such as `verification` and `behavioral contract` were treated as external-claim research signals, causing `research`, `external_doc_scout`, `ultra_review`, and preflight governance to activate for bounded repairs.

## Decision

- Strip benchmark contract suffixes before lexical signal classification.
- Keep `hyper_sprint` and `should_research` decoupled so bounded repair can stay on `hyper + repair_loop` without paying research overhead.
- Only activate `external_doc_scout` from `doc_scout_hits` when the route is explicitly in `claim_scout`, `architecture_scout`, or `benchmark_framer` mode, or when claim uncertainty is present.
- Keep preflight governance for real low-confidence/history-backed trust tasks, not for every public or repair task.

## Consequences

- Public hidden/repair tasks no longer inherit heavy research/governance stacks from benchmark wrapper text alone.
- Governance/public-report tasks still retain research and review coverage when their task body genuinely asks for it.
- Future route tuning should validate both benchmark-wrapped prompts and plain runtime prompts before promotion.
