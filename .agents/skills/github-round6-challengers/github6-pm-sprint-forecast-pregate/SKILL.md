---
name: github6-pm-sprint-forecast-pregate
description: Use for Nexus forecast_pregate work that must decide sprint scope, capacity, dependencies, and risk before execution. Do not use for generic product brainstorming or for runtime promotion without Flash+Nexus receipt evidence.
metadata: {"source_repo":"https://github.com/phuryn/pm-skills","source_commit":"020ee82501d9c09f9b989517c4cf9641bad057ff","source_status":"github_round6_prompt_only_rewrite","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Round6 PM Sprint Forecast Pregate

Use this skill as a prompt-only forecast/pregate discipline for execution planning.

## Boundary

- Do not commit to scope without capacity, dependency, and risk checks.
- Do not turn product planning into runtime default policy.
- Do not accept vague success criteria.

## Workflow

1. Define the sprint or execution window.
2. Estimate capacity:
   - available people or agent time
   - historical velocity or recent throughput
   - interruption buffer
3. Select work only after checking:
   - readiness
   - dependency chain
   - owner or executor
   - verification command
4. Identify the critical path and top risks.
5. Return `go`, `trim_scope`, or `block`.

## Output Contract

Return:

- `goal`
- `capacity`
- `selected_work`
- `dependencies`
- `risks`
- `pregate_decision`

Keep scope decisions explicit and reversible.
