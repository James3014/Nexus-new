---
name: sf2-learning_closure-route-fit-spec
description: Use when Nexus route capability is learning_closure and the task needs learning closure, lesson writeback, SLO/KPI closure matrix, and policy writeback evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: learning_closure
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-learning_closure-route-fit-spec

## Load when
SF2 spec candidate for learning_closure: lesson writeback, closure matrices, and learning KPI/SLO. Use when route capability is learning_closure. Required route terms: learning closure, lesson, writeback, slo, kpi, closure matrix, goal closure, closure executor, continuous optimization, autotune.

## Do not load when
- Runtime default mounting is requested.
- Public benchmark or production policy update is requested.
- The task does not match the declared capability_id.

## Evidence required
- Capability-only baseline row.
- Skill-arm row with selected/injected/used/evidence/outcome receipt.
- Negative-control row that BLOCKs or RETURNs.
- Runtime promotion review after SF2 verdict.

## Boundary
This asset is candidate-only. It may be used for SF2 ablation planning, but it must not be treated as a runtime skill default.
