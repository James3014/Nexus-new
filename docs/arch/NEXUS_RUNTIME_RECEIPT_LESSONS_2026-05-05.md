# Nexus Runtime Receipt Lessons - 2026-05-05

## Scope
This ADR records lessons from P321-P350 semantic runtime receipt integration.

## Lessons
- Plateau is detected after history is loaded, so capability planning must be refreshed after plateau detection. Otherwise `architecture_scout` can be required by runtime reality but absent from the selected plan.
- `semantic_searcher` receipt evidence must not depend on `NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR`. Semantic retrieval evidence is a memory/retrieval capability, while local swarm execution is only required for `swarm`, `drone`, `nightshift`, and `swarm_quiet_moment` bench receipts.
- Flash A/B timeout rows are not valid route-quality evidence. A run that exits before Nexus emits `nexus_usage_trace` must be classified as infra/runtime invalid, then rerun with an adequate gateway/subprocess budget before claiming route improvement.
- Provider seams that call local helper methods must be unit-tested through the provider boundary. A static/injected fetch provider failed when `_best_line` was called as an instance method from a provider, so fetched external evidence disappeared silently behind the fail-closed provider wrapper.
- `external_doc_scout` must not become public-safe from rejected claims alone. A runtime receipt needs at least one verified external source count, otherwise claim-scout selection can be mistaken for external fact verification.

## Applied Fixes
- Added late plateau replan before execution.
- Added runtime receipt payloads for `llm_judge_panel`, `asi_constraint_extractor`, `architecture_scout`, `external_doc_scout`, and `formal_report`.
- Decoupled `semantic_searcher` fixture evidence from the local swarm executor flag.
- Renamed the preferred semantic judge route capability to `judge_panel` while preserving `llm_judge_panel` compatibility keys for existing reports.
- Added provider/cache/source-count metadata to DocScout receipts and made the external DocScout gate require verified sources.

## Remaining Debt
- `swarm_quiet_moment` Flash path still needs a bounded non-timeout LLM profile before public A/B claims can include it.
