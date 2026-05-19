---
name: sf2-belief-route-fit-spec
description: Use when Nexus route capability is autoreason, belief and the task needs belief, autoreason confidence state, subjective route assessment, and decision evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata: {"capability_id":"belief","sf2_candidate_only":true,"runtime_eligible":false,"public_benchmark_allowed":false}
---

# sf2-belief-route-fit-spec

## Load when
SF2 spec candidate for belief: belief state, subjective confidence, and route priors. Use when route capability is belief. Required route terms: belief, confidence, prior, budget, doubt, careful, strategy, strategic.

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
