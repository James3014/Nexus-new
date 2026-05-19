---
name: sf2-swarm_multi_agent-route-fit-spec
description: Use when Nexus route capability is swarm_multi_agent and the task needs swarm and multi-agent orchestration, worktree delegation, submit/verify/integrate receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: swarm_multi_agent
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-swarm_multi_agent-route-fit-spec

## Load when
SF2 spec candidate for swarm_multi_agent: swarm, multi-agent, worktree, submit, verify, integrate. Use when route capability is swarm_multi_agent. Required route terms: swarm, multi-agent, worktree, fleet, integrate, submit.

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
