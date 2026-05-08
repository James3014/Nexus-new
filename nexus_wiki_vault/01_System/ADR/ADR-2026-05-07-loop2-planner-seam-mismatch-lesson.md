---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-07 Loop2 Planner Seam Mismatch Lesson

## Context

`Loop 2` targeted one narrow cost issue:

- hidden / repair should stop auto-opening `research`

The attempted change patched the standalone planner seam and passed local tests:

- hidden synthetic replay became gate-only
- repair synthetic replay removed `research`

But the benchmark rerun still showed runtime rows with:

- hidden selected `research`
- repair selected `research`
- tactical sequence still inserting `memory -> research`

## Finding

The planner seam and the runtime route seam are not the same optimization surface.

Fixing:

- `CapabilityPlanner`

did not automatically fix:

- the upstream runtime path that materializes `route["capability_plan"]`
- the tactical sequence later emitted into benchmark telemetry

## Decision

When a planner-only patch does not change runtime benchmark telemetry:

1. revert the planner-only patch from promotion
2. record the attempt as `HOLD`
3. patch the runtime route materialization seam next

## Consequence

This avoids a false positive where:

- unit tests improve
- benchmark telemetry looks unchanged
- we mistakenly claim route-cost progress

## Next Target

The next loop must instrument and patch the runtime route source that writes:

- `route["capability_plan"]`
- `route["route_decision"]`
- `route_tactical_sequence`

for the always-on Gemini benchmark path.
