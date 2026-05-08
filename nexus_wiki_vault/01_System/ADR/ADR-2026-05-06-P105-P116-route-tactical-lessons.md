---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-06 P105-P116 Route Tactical Lessons

## Context

P105-P116 strengthens the route/receipt layer before another Flash run:

- Autoreason candidate summaries must carry multi-hop evidence, not only stdout snippets.
- Capability routes must expose an auditable tactical sequence without inflating light tasks.
- OpenSeeker traces must include belief confidence receipts without storing reasoning text.

## Decision

Keep the new route fields additive under `stop_policy` and do not change the legacy
`selected_capabilities` contract in this slice.

## Failure-to-Lesson

### Simple doc tasks must not inherit deep tactical maps

Failure:

- `test_capability_router_keeps_simple_doc_fix_light` failed after the first tactical-map implementation.
- The route still returned legacy `selected_capabilities=["baseline"]`, but `stop_policy.tactical_sequence`
  exposed planner-selected research steps for a README typo.

Lesson:

- A diagnostic tactical map is still a routing surface. If it names tools for a light task, the route
  quality funnel can count it as over-selection even when the compatibility facade stays baseline-only.

Closure:

- Tactical sequence expansion is now gated behind deep-route signals: candidate readiness, hard signal,
  high risk, or cross-module work.
- Simple doc fixes remain `["baseline"]`.
