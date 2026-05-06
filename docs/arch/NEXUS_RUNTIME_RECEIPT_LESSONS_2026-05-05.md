# Nexus Runtime Receipt Lessons - 2026-05-05

## Scope
This ADR records lessons from P321-P350 semantic runtime receipt integration.

## Lessons
- Plateau is detected after history is loaded, so capability planning must be refreshed after plateau detection. Otherwise `architecture_scout` can be required by runtime reality but absent from the selected plan.
- `semantic_searcher` receipt evidence must not depend on `NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR`. Semantic retrieval evidence is a memory/retrieval capability, while local swarm execution is only required for `swarm`, `drone`, `nightshift`, and `swarm_quiet_moment` bench receipts.
- Flash A/B timeout rows are not valid route-quality evidence. A run that exits before Nexus emits `nexus_usage_trace` must be classified as infra/runtime invalid, then rerun with an adequate gateway/subprocess budget before claiming route improvement.
- Provider seams that call local helper methods must be unit-tested through the provider boundary. A static/injected fetch provider failed when `_best_line` was called as an instance method from a provider, so fetched external evidence disappeared silently behind the fail-closed provider wrapper.
- `external_doc_scout` must not become public-safe from rejected claims alone. A runtime receipt needs at least one verified external source count, otherwise claim-scout selection can be mistaken for external fact verification.
- Route/runtime tests may need explicit cache access because `uv` resolves through `/Users/jameschen/.cache/uv`. A sandbox denial is infrastructure noise, not a product regression, and should be retried with the approved `uv run pytest` path before changing code.
- Flash 4x1 can show real solve uplift while still failing promotion if a planned semantic judge is not executable at runtime. Runtime receipts must prune and record selected capabilities that were skipped by candidate-factory readiness, otherwise public-safe gates mistake planner intent for a capability claim.
- Runtime pruning must be reported as its own metric. Otherwise a PASS can hide planner/runtime mismatches and make route quality look clean without showing how much selection was removed after execution.
- Targeted pytest node names must be confirmed with `rg` before relying on them as evidence. A wrong node id can exit before running the intended assertions and create false validation confidence.
- Candidate-ranking capabilities need an explicit readiness estimate before planner selection. A simple repair can solve through `hyper` and `delivery_gate` while lacking enough A/B/AB candidates for `autoreason` or `judge_panel`.
- When route feature schema expands, schema-shape tests must be updated in the same change. Otherwise correct signal additions appear as regressions even when runtime behavior is unchanged.

## Applied Fixes
- Added late plateau replan before execution.
- Added runtime receipt payloads for `llm_judge_panel`, `asi_constraint_extractor`, `architecture_scout`, `external_doc_scout`, and `formal_report`.
- Decoupled `semantic_searcher` fixture evidence from the local swarm executor flag.
- Renamed the preferred semantic judge route capability to `judge_panel` while preserving `llm_judge_panel` compatibility keys for existing reports.
- Added provider/cache/source-count metadata to DocScout receipts and made the external DocScout gate require verified sources.
- Made plateau hard-pivot testing distinguish runtime regressions from sandbox cache access failures.
- Added runtime receipt plan pruning for unexecuted `judge_panel`/`llm_judge_panel` when Autoreason is skipped by candidate-factory readiness.
- Added benchmark row, summary, Flash summary, and Markdown report metrics for runtime-pruned capabilities.
- Added candidate-factory readiness signals and stopped legacy compatibility stacks from seeding ranking layers for single-candidate simple repairs.

## Remaining Debt
- `swarm_quiet_moment` Flash path still needs a bounded non-timeout LLM profile before public A/B claims can include it.
