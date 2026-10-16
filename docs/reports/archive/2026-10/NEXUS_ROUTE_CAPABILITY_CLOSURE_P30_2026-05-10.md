# Nexus Route Capability Closure P30 - 2026-05-10

## Goal

Confirm the new route can correctly select, invoke, and attach evidence for required Nexus capabilities across three execution views:

1. Codex-operated deterministic Nexus smoke.
2. Gemini Flash wearing Nexus.
3. Gemini Pro wearing Nexus.

The gate is about route/capability wiring, not claiming every model answer is public-safe. Model/gate failure must be reported separately from missing capability invocation.

## Result

P30 route capability wiring is closed for the required runtime capability set.

Required runtime capabilities:

- autoreason
- belief
- ddtree
- drone
- lancedb
- nightshift
- research
- semantic_searcher
- swarm
- swarm_quiet_moment
- ultra_review

All required capabilities are observed as selected, invoked, evidence-present, outcome-contributing, and public-safe somewhere in the three-arm matrix. Flash also demonstrates the important negative case: `autoreason` was selected, invoked, and evidence-present, but not public-safe because its gate did not pass. That is not a route-wiring miss; it is a model/gate outcome diagnostic.

## Implemented

- Added `scripts/ops/capability_invocation_matrix.py`.
- Added `tests/ops/test_capability_invocation_matrix.py`.
- Produced `.nexus/reports/capability_invocation_matrix_p30.json`.
- Reused `.nexus/reports/capability_route_smoke_summary.json` as the Codex-operated Nexus deterministic arm.

## Three-arm evidence

### Codex-operated Nexus smoke

- Source: `.nexus/reports/capability_route_smoke_summary.json`
- Status: passed
- Route oracle funnel:
  - selected->invoked: 0.9848
  - invoked->evidence: 1.0
  - evidence->outcome: 1.0
  - unnecessary selected: 0.0152
- Public-safe capabilities include:
  - artifact_gate, autoreason, belief, claim_gate, codeintel, ddtree, delivery_gate, drone, hyper, lancedb, memory, mempalace_gate, nightshift, research, semantic_searcher, swarm, swarm_quiet_moment, ultra_review

### Flash wearing Nexus

- Source: `.nexus/reports/p30_flash_receipt_first_autoreason_v4/with_nexus_1778421560.jsonl`
- Status: model/gate failed, but route wiring present
- Expected capability: autoreason
- autoreason selected: true
- autoreason invoked: true
- autoreason evidence_present: true
- autoreason gate_passed: false
- autoreason public_safe: false
- Diagnostic: `expected_capability_invoked_but_not_public_safe`, failure reason `evidence_without_gate_pass`

### Pro wearing Nexus

- Source: `.nexus/reports/p30_pro_receipt_first_autoreason_no_retry/with_nexus_1778421046.jsonl`
- Status: passed for expected capability route receipt
- Expected capability: autoreason
- autoreason public_safe: true

## Verification

```bash
uv run pytest -q tests/ops/test_capability_invocation_matrix.py tests/engine/test_capability_wiring_audit.py tests/ops/test_capability_route_smoke.py
# 23 passed in 0.17s

uv run python scripts/ops/capability_route_smoke.py --print-only
# passed=true

uv run python scripts/ops/capability_route_smoke.py
# wrote .nexus/reports/capability_route_smoke_summary.json, passed=true

uv run python scripts/ops/capability_invocation_matrix.py \
  --arm codex:.nexus/reports/capability_route_smoke_summary.json \
  --arm flash:.nexus/reports/p30_flash_receipt_first_autoreason_v4/with_nexus_1778421560.jsonl \
  --arm pro:.nexus/reports/p30_pro_receipt_first_autoreason_no_retry/with_nexus_1778421046.jsonl \
  --output .nexus/reports/capability_invocation_matrix_p30.json
# passed=true

uv run pytest -q \
  tests/benchmark/test_capability_ab_runner.py::test_expected_capability_invocation_coverage_tracks_call_without_outcome \
  tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_preserves_expected_autoreason_over_cost_cap \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_retry_can_be_disabled_for_receipt_oracle \
  tests/engine/test_capability_receipt_adapters.py \
  tests/engine/test_capability_receipt_policy.py \
  tests/engine/test_capability_routing_contracts.py \
  tests/engine/test_capability_planner.py \
  tests/ops/test_capability_invocation_matrix.py
# 110 passed in 0.50s
```

## Assessment of agent recommendations

The recommendation is useful but should not be treated as one single issue.

Accepted for next phase:

- Policy folding: reduce hard-coded fixture-specific route policy into risk/benefit/cost/lane formulas.
- Safety floor for budget downgrade: cost pruning must never remove core governance on high-risk tasks.
- Pending executor closure: `swarm`, `drone`, and `nightshift` are receipt-backed in smoke, but executor integration needs a separate real-runtime audit.
- S2T promotion path: shadow policy should become promotable only behind explicit A/B gates and rollback criteria.

Rejected as immediate P30 blocker:

- Directly unblocking `s2t_policy_draft` from shadow-only. Current tests intentionally assert shadow-only behavior. Promoting it without gated evidence would turn learning into uncontrolled runtime mutation.
- Treating Flash public-safe failure as missing capability wiring. The matrix now separates invocation evidence from public-safe outcome.

## Residual debt

- Flash autoreason arm still fails public-safe due `evidence_without_gate_pass`; this is a model/gate diagnostic, not a route miss.
- Real executor closure for `swarm`, `drone`, `nightshift` remains P31+ work.
- S2T learned policy remains shadow-only until promotion criteria exist.
- Route cost policy still needs folding and safety-floor pruning tests.
