# Nexus Route Cost P45 Flash Closure

Date: 2026-05-10

## Decision

Nexus can use `supervised_bare_first` safely only when it remains a verifier-gated proposal path.

This round keeps the governance contract:

- hidden verifier is required before supervised bare-first can be accepted;
- high-risk refactor/governance tasks cannot use supervised bare-first unless explicitly overridden;
- medium-risk feature tasks may use supervised bare-first only when policy explicitly enables it;
- supervised bare failure on low-risk lite repair routes goes directly to bounded Nexus rescue instead of wasting a second strict model call;
- local/Nexus rescue keeps the first weak-model attempt as model-use evidence.

## Changes

- Added high/medium risk admission checks for `supervised_bare_first`.
- Added `allow_medium_risk_supervised_bare_first` to route-cost policy loading.
- Added repair-specific decision contracts for timeout and merge invariant tasks.
- Preserved token/model evidence when supervised bare fails and Nexus performs bounded rescue.
- Marked Nexus usage valid after supervised-bare-failed rescue if semantic completion is verified.

## Flash Evidence

Primary run: `.nexus/reports/flash_8x1_public_value_strict_p39/evidence_bundle.json`

- Public claim gate: PASS.
- Same model / same tasks: true.
- Hidden verifier mode: true.
- With Nexus semantic verified: 8/8.
- Bare semantic verified: 6/8.
- Trust mismatch: 0.0 / 0.0.
- Nexus usage valid rate: 1.0.
- Model uses Nexus rate: 1.0.
- Claim verified rate: 1.0.
- Wall ratio: 1.9298x.
- Median paired wall ratio: 1.2147x.
- Token ratio: 1.0399x.
- Provider token measured rate: 0.875.

Earlier baseline: `.nexus/reports/flash_8x1_public_value_strict_p28/evidence_bundle.json`

- Wall ratio: 2.3583x.
- Token ratio: 1.0278x.
- Hidden retry wall: non-zero on retry-heavy rows.

Cost delta:

- Wall ratio improved from 2.3583x to 1.9298x.
- Median paired wall ratio improved to 1.2147x.
- Hidden retry wall dropped to 0.0s in the final full run.

## Hotspot Evidence

Targeted run: `.nexus/reports/flash_retry_hot2_strict_p37/evidence_bundle.json`

- Nexus: 2/2 verified.
- Bare: 1/2 verified.
- Trust mismatch: 0.0 / 0.0.
- Nexus avg wall: 13.3782s.
- Bare avg wall: 15.3445s.
- Hidden retry wall: 0.0s.
- Token/provider measured rate: 1.0.

This shows the retry-heavy repair/evidence path can be made cheaper than bare while keeping verified delivery.

## Residual Debt

- Governance/refactor rows still have wall-time outliers, especially `nexus-value-gov-001` and `nexus-value-gov-002`.
- One governance row still has local rescue with missing provider tokens; current public gate passes because rate remains above threshold, but this is not closure-grade cost evidence.
- Next work should target governance/refactor bounded rescue telemetry and runner overhead, not weaken verifier/claim gates.

## Verification

- `uv run pytest -q tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/engine/test_capability_receipt_adapters.py tests/nexus/codeintel/test_dci_locator.py`
- Result: 255 passed.
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
- Result: passed=true.
