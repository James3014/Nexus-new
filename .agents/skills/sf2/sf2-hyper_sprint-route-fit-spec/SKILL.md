---
name: sf2-hyper_sprint-route-fit-spec
description: Use when Nexus route capability is hyper_sprint and the task needs hyper sprint repair, fast multi-candidate fixes, quick local recovery, and sprint evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: hyper_sprint
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-hyper_sprint-route-fit-spec

## Load when
SF2 spec candidate for hyper_sprint: fast multi-candidate local repair and sprint execution. Use when route capability is hyper_sprint. Required route terms: hyper, sprint, multi-candidate, quick fix, fast path.

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
