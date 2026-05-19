---
name: sf2-sandbox_replay-route-fit-spec
description: Use when Nexus route capability is sandbox_replay and the task needs sandboxed execution, replay validation, isolation checks, rerun evidence, and trace receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: sandbox_replay
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-sandbox_replay-route-fit-spec

## Load when
SF2 spec candidate for sandbox_replay: sandboxed execution, replay validation, isolation checks, and rerun evidence. Use when route capability is sandbox_replay. Required route terms: sandbox, replay, isolation, rerun, test runner, execution trace.

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
