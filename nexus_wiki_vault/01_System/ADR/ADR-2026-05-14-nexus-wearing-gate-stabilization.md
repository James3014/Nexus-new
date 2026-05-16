---
type: ADR
status: accepted
tags: [nexus, ADR, bench, stability, governance]
---

# ADR-2026-05-14: Nexus Wearing Gate Stabilization and Public Gate Builder Extraction

## Context

During the rollout of the P130 launch candidate, we observed "phantom failures" in benchmarks where tasks would pass behaviorally but fail governance checks because the Nexus "wearing" state (the active involvement of the governance engine) was either unevidenced or intermittently dropped during high-load swarming.

Furthermore, the logic for building public-safe gate checks was tightly coupled with the benchmark runner, making it difficult to reuse the same validation logic in production `closeout` flows.

## Decision

1. **Mandatory Nexus Wearing Gate**: All benchmark and production tasks must pass a `Wearing Gate` check. This check verifies that the `AutonomicRouter` and `HarnessSensors` were active and that their signals were captured in the `CapabilityReceipts`.
2. **Extraction of Public Gate Builder**: The logic for synthesizing `gate_verdict` and `public_claim_safe` status has been extracted into a standalone `PublicGateChecksBuilder`.
3. **Fail-Closed Evidence**: If a task description or oracle contract explicitly requires a capability (e.g., `lancedb`), the gate must fail if that capability's receipt is missing or unverified, regardless of the overall task success.

## Implementation Details

- **Files modified**:
    - `scripts/bench/benchmark_eligibility.py`: Added `is_nexus_wearing()` check.
    - `scripts/bench/capability_ab_runner.py`: Integrated the new builder.
    - `nexus/engine/completion_enforcer.py`: Now uses the same `gate_verdict` logic for production closeout.
- **Commit**: `41e05c3d`

## Consequences

- Improved credibility of benchmark results; "Passed" now implies "Governed and Evidenced".
- Reusable governance logic across development and production environments.
- Clearer diagnostic path for identifying why a route was penalized or protected.

## Lesson

Stability in a governance-first system requires that the "governance of the governor" (the Wearing Gate) be as robust as the tasks themselves. Evidence is not an optional artifact; it is the product.
