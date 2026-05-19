---
name: sf2-nightshift-route-fit-spec
description: Use when Nexus route capability is nightshift and the task needs nightshift long-running recovery, autonomous repair continuation, and delayed evidence closure; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: nightshift
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-nightshift-route-fit-spec

## Load when
SF2 spec candidate for nightshift: long-running recovery after normal repair fails. Use when route capability is nightshift. Required route terms: nightshift, night shift, longrun, long-running, recovery, emergency recovery, autonomous task, continuous optimization.

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
