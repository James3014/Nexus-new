---
name: github4-sickn33-antigravity-awesome-skills-ad-creative
description: "Use for benchmark_meta_opt candidate experiments that need structured variation design, metric-driven iteration, and experiment packaging. This is a prompt-only SF challenger adapted from sickn33/antigravity-awesome-skills ad-creative; do not use for runtime default, external ad-platform access, file mutation, package installation, or public benchmark claims."
metadata: {"source_repo":"https://github.com/sickn33/antigravity-awesome-skills","source_commit":"9e5d4ddefa24be7b50cc83f56a2450401cdf3317","source_path":"skills/ad-creative/SKILL.md","source_status":"external_challenger_rewritten_prompt_only","runtime_eligible":true,"ablation_eligible":true}
---

# GitHub Round4B Ad Creative Benchmark Meta-Optimization Candidate

## Load when
- Nexus is running an internal SF ablation for `benchmark_meta_opt`.
- The task needs experiment variants, metric hypotheses, comparison buckets, or iteration plans.
- The expected output is a receipt-backed benchmark or meta-optimization plan, not production ad copy.

## Do not load when
- The workflow would call ad platforms, APIs, external tools, or remote services.
- The task asks to install packages, execute upstream scripts, edit global rules, or mutate runtime policy.
- The result would be used as a public benchmark claim without a separate public-lane gate.

## Operating contract
- Stay prompt-only.
- Produce structured benchmark variants with measurable hypotheses.
- Keep delivery, cost, and promotion claims separate.
- Include explicit evidence requirements, expected failure modes, and next-run decision criteria.

## Required receipt fields
- `selected`
- `injected`
- `used`
- `evidence_present`
- `gate_passed`
- `outcome_contributed`

## Output shape
Return a compact benchmark-meta plan with:

1. Candidate variants.
2. Measurement target for each variant.
3. Risk or confounder per variant.
4. Decision rule for keep, reject, or rerun.
5. Evidence bundle requirements.

