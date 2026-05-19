---
name: sf2-forecast_pregate-route-fit-spec
description: Candidate-only SF2 route-fit skill for forecast_pregate.
metadata:
  capability_id: forecast_pregate
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-forecast_pregate-route-fit-spec

## Load when
SF2 spec candidate for forecast_pregate: forecast, pregate, plan quality, and risk prediction. Use when route capability is forecast_pregate. Required route terms: forecast, pregate, plan quality, risk, planner.

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
