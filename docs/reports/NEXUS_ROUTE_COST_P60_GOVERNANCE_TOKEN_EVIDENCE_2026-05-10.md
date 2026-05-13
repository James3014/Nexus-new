# NEXUS_ROUTE_COST_P60_GOVERNANCE_TOKEN_EVIDENCE_2026-05-10

## Task
Close the P46-P60 governance cost evidence gap: a Nexus bounded rescue after a model attempt must not be treated as clean public cost evidence when the model call has no provider token telemetry.

## Change
- Added a fail-closed eligibility rule for `nexus_bounded_rescue_after_model_attempt` rows with `model_calls > 0` and no measured tokens.
- Kept generic zero-token rows as token-unreliable rather than infra-invalid, preserving existing report semantics.
- Added regression coverage for the bounded-rescue token gap.

## Verification
- `uv run pytest -q tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/engine/test_capability_receipt_adapters.py tests/nexus/codeintel/test_dci_locator.py`
  - PASS: 256 tests.
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
  - PASS.
- Flash governance hot2 A/B:
  - Output: `.nexus/reports/flash_gov_hot2_token_gate_p47/evidence_bundle.json`
  - Public claim gate: PASS.
  - With Nexus: 2/2 semantic verified.
  - Bare Gemini 3 Flash: 1/2 semantic verified.
  - Trust mismatch: 0.0.
  - Provider token measured rate: 1.0 for both arms.
  - Clean model cost evidence rate: 1.0 for Nexus.
  - Avg wall with Nexus: 34.3663s.
  - Avg wall bare: 16.4519s.
  - Wall ratio: 2.0889x.
  - Token ratio: 1.0383x.

## Interpretation
The prior P39 failure mode is closed: governance rows can no longer silently count a model attempt with zero provider tokens as valid public cost evidence after local rescue.

The remaining cost issue is not token evidence. It is governance R-phase wall time:
- Avg Nexus R phase wall: 23.7087s.
- `rlm-harder-v2-governance-001`: R phase 36.3370s.
- `rlm-harder-v2-governance-002`: R phase 11.0803s.

## Residual Debt
- Governance route still costs ~2.09x wall vs bare on hot2, while the public target is <= 1.8x.
- Next optimization should cap or specialize governance R-phase execution without removing MemPalace / Claim / Artifact / Delivery gates.
