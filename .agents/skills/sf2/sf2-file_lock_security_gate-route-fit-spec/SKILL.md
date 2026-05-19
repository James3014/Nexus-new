---
name: sf2-file_lock_security_gate-route-fit-spec
description: Use when Nexus route capability is file_lock_security_gate and the task needs file lock, delegated execution safety, sandbox permission, and security gate evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: file_lock_security_gate
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-file_lock_security_gate-route-fit-spec

## Load when
SF2 spec candidate for file_lock_security_gate: file-lock and delegated execution safety boundaries. Use when route capability is file_lock_security_gate. Required route terms: file lock, lock, security gate, permission, sandbox permission.

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
