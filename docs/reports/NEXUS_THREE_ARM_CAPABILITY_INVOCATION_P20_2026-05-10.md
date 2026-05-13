# Nexus Three-Arm Capability Invocation P20

## Goal

Verify that the new route can call the capabilities it is supposed to use, without confusing model solve failure with route/receipt wiring failure.

## Result

P20 route invocation gate: PASS.

This is not a public benchmark improvement claim. It is an internal capability invocation and receipt diagnostic.

## What Changed

- Added `NEXUS_CAPABILITY_RECEIPT_FIRST=1` support in `scripts/bench/capability_ab_runner.py`.
- Added `expected_capability_invocation_coverage` so benchmark rows can distinguish:
  - capability selected/invoked/evidence present
  - capability public-safe/outcome-contributed
  - model solve success/failure
- Extended Codex wearing-Nexus path so receipt-first probes receive executor flags.

## Three-Arm Benchmark Evidence

Task: `route-oracle-autoreason-001`

| Arm | Nexus wearing valid | Expected invocation | Public-safe receipt | Solve | Notes |
| --- | --- | --- | --- | --- | --- |
| Codex+Nexus (`gpt-5.5`) | true | PASS | FAIL | FAIL | `autoreason` selected/invoked/evidence, but no outcome contribution. |
| Flash+Nexus (`gemini-3-flash-preview`) | true on 240s retry | PASS | FAIL | FAIL | `autoreason` selected/invoked/evidence; high cost: 202027 tokens, 4 calls, R phase 154.7367s. |
| Pro+Nexus (`gemini-3.1-pro-preview`) | true | PASS | PASS | FAIL | `autoreason` public-safe receipt exists; task still semantic UNVERIFIED. |

Evidence files:

- `.nexus/reports/p20_codex_receipt_first_autoreason_v2/with_nexus_1778388925.jsonl`
- `.nexus/reports/p20_flash_receipt_first_autoreason_240s/with_nexus_1778389718.jsonl`
- `.nexus/reports/p20_pro_receipt_first_autoreason/with_nexus_1778389228.jsonl`

## Full Route Smoke Evidence

Command: `uv run python scripts/ops/capability_route_smoke.py`

Result: PASS.

Summary file: `.nexus/reports/capability_route_smoke_summary.json`

Coverage:

| Suite | Tasks | Expected capabilities | Public-safe capabilities | Selected -> Invoked | Invoked -> Evidence | Evidence -> Outcome | Unnecessary Selected |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| route_oracles | 8 | autoreason, ddtree, drone, lancedb, nightshift, research, swarm, ultra_review | same 8 | 0.9848 | 1.0 | 1.0 | 0.0152 |
| codeintel_hyper | 2 | codeintel, delivery_gate, hyper, memory | same 4 | 1.0 | 1.0 | 1.0 | 0.0 |
| core_governance_gates | 2 | artifact_gate, claim_gate, mempalace_gate | same 3 | 1.0 | 1.0 | 1.0 | 0.0 |
| belief_gate | 1 | belief | belief | 1.0 | 1.0 | 1.0 | 0.0 |
| runtime_receipt_oracles | 2 | semantic_searcher, swarm_quiet_moment | same 2 | 1.0 | 1.0 | 1.0 | 0.0 |

## Verification Commands

```bash
uv run pytest -q \
  tests/benchmark/test_capability_ab_runner.py::test_expected_capability_invocation_coverage_tracks_call_without_outcome \
  tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_receipt_first_preserves_capability_on_model_timeout \
  tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_preserves_expected_autoreason_over_cost_cap
```

Result: `3 passed`.

```bash
uv run pytest -q \
  tests/engine/test_capability_wiring_audit.py \
  tests/engine/test_capability_receipt_adapters.py \
  tests/engine/test_capability_routing_contracts.py \
  tests/engine/test_capability_planner.py
```

Result: `102 passed`.

```bash
uv run python scripts/ops/capability_route_smoke.py --print-only
uv run python scripts/ops/capability_route_smoke.py
```

Result: both PASS.

## Residual Debt

- Flash+Nexus now proves invocation under 240s, but solve remains UNVERIFIED and cost is too high. Next work should optimize Flash R-phase and prompt/candidate budget, not route wiring.
- Codex+Nexus direct model path proves invocation via receipt-first, but direct solve remains UNVERIFIED. Treat as model outcome issue, not capability wiring issue.
- Pro+Nexus produced a public-safe `autoreason` receipt but still failed final semantic verification. Next triage should inspect patch/output quality rather than route selection.
