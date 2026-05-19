---
name: sf2-direct_master_loop-route-fit-spec
description: Use when Nexus route capability is direct_master_loop and the task needs direct master loop execution, default task control, content rewrite, and execution receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: direct_master_loop
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-direct_master_loop-route-fit-spec

## Load when
SF2 spec candidate for direct_master_loop: default execution loop and content/rewrite control. Use when route capability is direct_master_loop. Required route terms: direct, master loop, rewrite, content, execute, task.

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
