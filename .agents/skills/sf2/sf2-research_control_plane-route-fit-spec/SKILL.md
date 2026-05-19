---
name: sf2-research_control_plane-route-fit-spec
description: Candidate-only SF2 route-fit skill for research_control_plane.
metadata:
  capability_id: research_control_plane
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-research_control_plane-route-fit-spec

## Load when
SF2 spec candidate for research_control_plane: research planning, source conflict handling, and research gates. Use when route capability is research_control_plane. Required route terms: source conflict, source validation, citation chain, claim verification, academic verify.

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
