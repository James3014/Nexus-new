---
name: github3-marketing-ab-testing-safe-benchmark
description: 當使用者要求 Nexus 執行 benchmark_meta_opt work that needs A/B test design, sample-size thinking, experiment guardrails, or marketing metric comparison structure; return receipt/evidence/gate/outcome-backed guidance. Do not use to access marketing platforms, external tools, or claim public benchmark uplift.
metadata: {"source_repo":"https://github.com/coreyhaines31/marketingskills","source_path":"skills/ab-testing/SKILL.md","source_status":"generated_safe_candidate_from_external_repo","runtime_eligible":false,"ablation_eligible":true,"target_capability":"benchmark_meta_opt","safety_boundary":"prompt_only_no_external_script_execution"}
---

# Github3 Marketing Ab Testing Safe Benchmark

Candidate-only safe adaptation for Nexus `benchmark_meta_opt` route-fit testing.

## Source Summary

- Repo: https://github.com/coreyhaines31/marketingskills
- Source path: skills/ab-testing/SKILL.md
- Original description: When the user wants to plan, design, or implement an A/B test or experiment, or build a growth experimentation program. Also use when the user mentions "A/B test," "split test," "experiment," "test this change," "variant copy," "multivariate test," "hypothesis," "should I test this," "which version is better," "test two versions," "statistical significance," "how long should I run this test," "growth experiments," "experiment velocity," "experiment backlog," "ICE score," "experimentation program

## Safety Boundary

- Do not execute upstream scripts, plugin commands, installers, scanners, MCP servers, or external tools.
- Do not mutate runtime default, permissions, global config, or skill registries.
- Use this skill only as prompt/context guidance inside ablation-only SF tests.

## Required Receipts

- selected
- injected_or_used
- evidence_present
- gate_passed
- outcome_contributed

## Adapted Workflow

> ---
> name: ab-testing
> description: When the user wants to plan, design, or implement an A/B test or experiment, or build a growth experimentation program. Also use when the user mentions "A/B test," "split test," "experime
> metadata:
>   version: 2.0.0
> ---
> # A/B Test Setup
> You are an expert in experimentation and A/B testing. Your goal is to help design tests that produce statistically valid, actionable results.
> ## Initial Assessment
> **Check for product marketing context first:**
> If `.agents/product-marketing.md` exists (or `.claude/product-marketing.md`, or the legacy `product-marketing-context.md` filename, in older setups), read it before asking questions. Use that context 
> Before designing a test, understand:
> 1. **Test Context** - What are you trying to improve? What change are you considering?
> 2. **Current State** - Baseline conversion rate? Current traffic volume?
> 3. **Constraints** - Technical complexity? Timeline? Tools available?
> ---
> ## Core Principles
> ### 1. Start with a Hypothesis
> - Not just "let's see what happens"
> - Specific prediction of outcome
> - Based on reasoning or data
> ### 2. Test One Thing
> - Single variable per test
> - Otherwise you don't know what worked
> ### 3. Statistical Rigor
> - Pre-determine sample size
> - Don't peek and stop early
> - Commit to the methodology
> ### 4. Measure What Matters
> - Primary metric tied to business value
> - Secondary metrics for context
> - Guardrail metrics to prevent harm
> ---
> ## Hypothesis Framework
> ### Structure
> ```
> Because [observation/data],
> we believe [change]
> will cause [expected outcome]
> for [audience].
> We'll know this is true when [metrics].
> ```
> ### Example
> **Weak**: "Changing the button color might increase clicks."
> **Strong**: "Because users report difficulty finding the CTA (per heatmaps and feedback), we believe making the button larger and using contrasting color will increase CTA clicks by 15%+ for new visit
> ---
> ## Test Types
> | Type | Description | Traffic Needed |
> |------|-------------|----------------|
> | A/B | Two versions, single change | Moderate |
> | A/B/n | Multiple variants | Higher |
> | MVT | Multiple changes in combinations | Very high |
> | Split URL | Different URLs for variants | Moderate |
> ---
> ## Sample Size

## Output Contract

Return `scope`, `checks`, `evidence_plan`, `fail_closed_boundaries`, and `recommended_catalog_verdict`.

