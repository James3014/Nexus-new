---
name: sf2-delivery_acceptance_gate-route-fit-spec
description: Candidate-only SF2 route-fit skill for delivery_acceptance_gate.
metadata:
  capability_id: delivery_acceptance_gate
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-delivery_acceptance_gate-route-fit-spec

## Load when
SF2 spec candidate for delivery_acceptance_gate: delivery gate, acceptance check, and contract checks. Use when route capability is delivery_acceptance_gate. Required route terms: delivery, acceptance, contract, done criteria.

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
