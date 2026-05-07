# ADR-2026-05-08: Lite Route Must Preserve Cheap Verified Solver Flow

## Status

Accepted

## Context

P51-P60 compared Gemini 3 Flash bare runs with Nexus-wearing runs for route-cost tuning. Two task classes showed confirmed over-governance: bare Flash already verified the task, while full Nexus still selected costly ranking/review layers. The first lite-route implementation attempted to reduce cost by forcing the benchmark runner from `hyper_sprint` to `baseline`.

That was the wrong abstraction boundary. `hyper_sprint` owns deterministic local-preflight paths for small verified benchmark families. Forcing `baseline` removed high-cost route selection but also bypassed the cheap verified path, making the lite route slower instead of cheaper.

## Decision

Lite route preserves the selected solver flow and only changes cost controls around it:

- Cap candidate count to 1.
- Disable LLM self-heal for lite-route tasks.
- Downgrade high-cost conditional capabilities such as `autoreason`, `judge_panel`, `ultra_review`, `sandbox`, swarm/collaboration, and external research layers.
- Keep fail-closed governance and delivery gates selected.
- If candidate factory readiness is `SKIPPED`, ranking layers must remain unselected even when learning policy would otherwise promote them.

## Consequences

Local-preflight success is valid as Nexus-internal delivery evidence, but it is not provider-token evidence and must not be reported as model uplift. Route-cost reports must separate:

- Model uplift: provider-measured verified model calls improve.
- Cost avoidance: Nexus uses deterministic verified paths and avoids model calls.

## Evidence

- `nexus-value-gov-001`: full Nexus was `53.70s` with one Flash call; lite route after preserving `hyper_sprint` was `3.65s` with zero model calls.
- `nexus-value-evidence-001`: full Nexus was `54.58s` with two Flash calls; lite route after preserving `hyper_sprint` was `3.65s` with zero model calls.
- Pre-Flash gate now confirms `candidate_count=1` repair routes keep `autoreason` and `judge_panel` out of the selected plan.
