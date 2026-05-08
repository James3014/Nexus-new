---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-07 Hidden Route Cost Truth Lesson

## Context

We reduced the hidden-bugfix route from a 9-capability stack to a 4-capability micro-patch lane:

- before: `research_route`, `delivery_gate`, `mempalace_gate`, `artifact_gate`, `claim_gate` + `memory`, `asi_constraint_extractor`, `belief`, `direct_mode`
- after: `delivery_gate`, `mempalace_gate`, `artifact_gate`, `claim_gate`

The route became structurally smaller, but the measured Flash benchmark cost did not improve on the sampled hidden task.

## Observation

On `nexus-value-hidden-001`:

- selected capability count dropped from `9` to `4`
- verified success stayed `1/1`
- wall time and tokens did not improve enough to support a cost claim

This means route selection count was not the only dominant cost driver.

## Lesson

Reducing selected capabilities is necessary but not sufficient for weak-model cost reduction.

For low-risk hidden bugfix tasks, the remaining overhead can still be dominated by:

- runtime orchestration framing
- context assembly
- prompt-wearing scaffolding
- phase/reporting envelope cost

## Decision

When cost truth shows `selected_count` improvement without wall/token improvement:

1. Keep the route reduction if it does not regress success or trust.
2. Do not claim cost improvement from route slimming alone.
3. Move the next optimization target to runtime/context overhead, not just planner selection.

## Follow-up

- Add cost-truth comparisons against `GPT-5.4 direct` and `GPT-5.5 direct`.
- Investigate prompt/context payload size for `L0_micro_patch`.
- Separate planner savings from orchestration savings in future reports.
