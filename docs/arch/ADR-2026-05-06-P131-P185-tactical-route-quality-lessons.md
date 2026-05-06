# ADR-2026-05-06 P131-P185 Tactical Route Quality Lessons

## Context

P131-P185 connects route tactical telemetry to benchmark reports and route-quality gates.
The goal is to ensure an evidence-required tactical tool cannot be advertised by the
route without either a runtime receipt or a fail-closed route-quality penalty.

## Decision

Only `tactical_tool_map` entries with `evidence_required=true` are joined into
route-quality counts. Bookkeeping sequence entries are not counted.

## Failure-to-Lesson

### JSONL compatibility must parse the serialized tactical map

Failure:

- `test_summarize_jsonl_counts_evidence_required_tactical_gap_as_over_selection`
  failed with `selected_total == 1` instead of `2`.
- The helper read `route_tactical_tool_map` first and received the fallback empty list,
  so it never parsed `route_tactical_tool_map_json`.

Lesson:

- Benchmark JSONL rows often carry serialized fields for portability. A fallback empty
  container is not equivalent to an intentionally present empty runtime field.

Closure:

- `_route_tactical_tool_map` now falls through to `route_tactical_tool_map_json` when
  the direct list is absent or empty.

### Tactical policy must be generated at the canonical route decision seam

Failure:

- A Flash 2x1 run passed delivery/cost gates but reported `route_tactical_tool_count=0`
  for with-Nexus rows.
- The tactical map existed in the compatibility `CapabilityRouter` facade, but actual
  auto-flow rows use `build_route_decision()` from `route_decision_adapter`.

Lesson:

- Report-only telemetry is not enough. Tactical routing must be emitted from the same
  canonical route decision seam used by runtime and benchmark extraction.

Closure:

- `build_route_decision()` now fills `stop_policy.tactical_sequence` and
  `stop_policy.tactical_tool_map` by default when callers do not provide one.

### Tactical-policy tests must use real planner signals

Failure:

- The first `route_tactical_policy` extraction test assumed a high-risk task always
  selects `belief`.
- The planner only selects `belief` when confidence/budget signals require it.

Lesson:

- A refactor test must preserve the planner's real selection semantics instead of
  hard-coding a desired tactical sequence.

Closure:

- The test now supplies low root-cause confidence before asserting belief ordering.
