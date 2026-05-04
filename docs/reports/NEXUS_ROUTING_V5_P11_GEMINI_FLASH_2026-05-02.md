# Nexus Routing v5 P11 - Gemini 3 Flash Benchmark Snapshot (2026-05-02)

## Scope
- Model: `gemini-3-flash-preview`
- Comparison: same-model `bare` vs `wearing Nexus`
- Routing baseline: v5 tiering + hazard mapping + early-exit contract + legacy override fail-closed marker
- Public-safe manifests: execution-safe + disclosure pair

## Lane Results

### 1) Cost Efficiency (6 tasks)
- Output dir: `.nexus/reports/bench_gemini_flash_cost_v5_p11`
- Public claim gate: `PASS`
- With Nexus:
  - eligible solve rate: `1.0`
  - semantic verified: `1.0`
  - trust mismatch: `0.0`
  - avg wall: `56.55s`
  - avg tokens: `24179.83`
- Bare:
  - eligible solve rate: `0.5`
  - semantic verified: `0.5`
  - trust mismatch: `0.0`
  - avg wall: `24.12s`
  - avg tokens: `23387.83`
- Readout: +50pp solve/verified uplift with Nexus, but with higher wall time and slightly higher tokens.

### 2) Capability Lift (6 tasks)
- Output dir: `.nexus/reports/bench_gemini_flash_caplift_v5_p11`
- Public claim gate: `FAIL`
- With Nexus:
  - total/eligible: `6/5` (1 infra invalid: `nexus_delivery_invalid`)
  - eligible solve rate: `0.6`
  - semantic verified: `0.6`
  - trust mismatch: `0.4`
  - avg wall: `66.97s`
  - avg tokens: `29783.8`
- Bare:
  - total/eligible: `6/6`
  - eligible solve rate: `0.3333`
  - semantic verified: `0.3333`
  - trust mismatch: `0.0`
  - avg wall: `34.85s`
  - avg tokens: `25616.5`
- Readout: capability uplift exists, but this run is not public-claim safe due to trust mismatch + eligibility mismatch.

### 3) Governed Delivery (5 tasks, leak task excluded)
- Output dir: `.nexus/reports/bench_gemini_flash_governed_v5_p11`
- Public claim gate: `PASS`
- With Nexus:
  - eligible solve rate: `1.0`
  - semantic verified: `1.0`
  - trust mismatch: `0.0`
  - avg wall: `56.57s`
  - avg tokens: `26118.6`
- Bare:
  - eligible solve rate: `1.0`
  - semantic verified: `1.0`
  - trust mismatch: `0.0`
  - avg wall: `35.67s`
  - avg tokens: `24883.8`
- Readout: governance lane parity on success metrics; Nexus adds overhead but keeps delivery trust-clean.

## Preflight/Gating Notes
- `capability_lift` preflight: PASS
- `cost_efficiency` preflight: PASS
- `governed_delivery` preflight: FAIL on `prompt_leak:nexus-value-trust-002`
  - Operational action in this run: excluded `nexus-value-trust-002` via `--task-id-filter`

## Routing v5 Impact Notes
- Contract now emits tier/hazard/pruning/early-exit fields in route decision.
- Legacy override marker is present and smoke-gated (`legacy_override_detected` triggers failure).
- P11 status: route contract hardening completed; benchmark quality improved, but capability-lift lane still needs trust-mismatch cleanup before public claim.

## Required Follow-up (before final public report)
1. Fix `nexus_delivery_invalid` path in capability-lift lane (eligibility completeness).
2. Remove with-Nexus trust mismatch in capability-lift lane (`with_trust_mismatch_rate` from `0.4` -> `0.0`).
3. Resolve governed preflight prompt leak in `nexus-value-trust-002`, then rerun full 6/6 governed lane.
