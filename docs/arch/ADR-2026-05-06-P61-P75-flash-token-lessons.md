# ADR-2026-05-06: P61-P75 Flash Token Evidence Lessons

## Status

Accepted

## Context

P61-P75 connected OpenSeeker trajectory metrics to the public benchmark evidence bundle and extended ASI records with trajectory step counts so low-information trajectories do not become cross-task constraints.

The Flash smoke runs showed Nexus functionality improved verified delivery on the sampled tasks, but the public claim gate stayed blocked by incomplete token evidence on long-running context rows.

## Decisions

1. Treat `trajectory_step_count=0` as unknown rather than low-step evidence.
2. Filter ASI constraints only when `0 < trajectory_step_count < MIN_EVOLUTION_STEPS`.
3. Publish OpenSeeker benchmark KPIs in `evidence_bundle.json` as trajectory-richness telemetry, not as training-quality claims.
4. Do not claim public token/cost improvement when rows use `model_timeout_with_local_fallback`.

## Lessons

1. Invalid pytest node ids waste verification time. Use `rg -n "def test_..."` before targeted pytest commands when the test name is not certain.
2. Backward-compatible numeric fields need an explicit unknown value. Default `0` on historical `ASIRecord` rows must not be interpreted as a low-step trajectory.
3. Gateway timeout tuning can improve token capture, but long-tail model calls still need a separate cost-evidence strategy. Local fallback can prove delivery, not provider token comparability.

## Evidence

- `tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle`: PASS after adding OpenSeeker bundle KPI assertions.
- `tests/engine/test_asi_constraints.py`: PASS after fixing `trajectory_step_count=0` semantics.
- Flash 2x2, timeout 120/gateway 90: with-nexus 4/4 verified, without-nexus 0/4 verified, public claim gate FAIL due `with_token_measured_below_threshold` at 0.5.
- Flash 2x2, timeout 180/gateway 150: with-nexus 4/4 verified, without-nexus 0/4 verified, public claim gate FAIL due `with_token_measured_below_threshold` at 0.75.
- Flash 2x1, timeout 210/gateway 190: with-nexus 2/2 verified, without-nexus 1/2 verified, token reliability still 0.5 due context-row model timeout with local fallback.

## Follow-up

P76 should separate verified-delivery claims from public token/cost claims and either add a measured-token rescue receipt from the model gateway or mark timeout-rescued rows as delivery-valid but cost-ineligible in a way the public gate can audit explicitly.
