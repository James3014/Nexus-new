# Nexus DCI + R-Timing Route Cost Closure P21

## Status

PARTIAL closure. Correctness and trust safety held, but cost did not improve on Flash hot4.

## Changes

- Added a scoped DCI evidence locator for CodeIntel evidence-heavy tasks.
- Attached DCI report paths and evidence refs to CodeIntel receipts.
- Added R-phase sub-timing fields so route-cost regressions can identify whether the wall time is Hyper/model-call driven.
- Narrowed DCI default admission after Flash hot4 showed DCI was opening on governance/trust lanes without cost benefit.

## Verification

- `python3 -m py_compile nexus/services/codeintel/dci_locator.py nexus/app/research_flow_service.py nexus/engine/capability_receipt_adapters.py scripts/bench/capability_ab_runner.py`
- `uv run pytest -q tests/nexus/codeintel/test_dci_locator.py tests/engine/test_capability_receipt_adapters.py tests/app/test_research_flow_service.py tests/benchmark/test_capability_ab_runner.py -k 'dci or codeintel or extract_record'`
  - `12 passed`
- `uv run pytest -q tests/nexus/codeintel/test_dci_locator.py tests/engine/test_capability_receipt_adapters.py tests/app/test_research_flow_service.py tests/benchmark/test_capability_ab_runner.py`
  - `246 passed`
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
  - `passed=true`
- Flash hot4 same-model A/B:
  - command output dir: `.nexus/reports/flash_hot4_dci_rtiming_p21`
  - with_nexus: `4/4`, semantic verified `1.0`, trust mismatch `0.0`
  - without_nexus: `4/4`, semantic verified `1.0`, trust mismatch `0.0`
  - with_nexus avg wall: `59.9266s`
  - without_nexus avg wall: `25.8996s`
  - with_nexus avg R phase wall: `49.8402s`
  - with_nexus avg R hyper sprint wall: `49.8398s`

## Evidence

The post-change row data shows the next bottleneck is R phase/model-call wall time:

| task | with_nexus wall | R phase | R hyper | DCI | tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| nexus-value-gov-002 | 75.4567 | 65.0334 | 65.0330 | yes | 52786 |
| nexus-value-context-002 | 43.4149 | 32.0114 | 32.0109 | yes | 46750 |
| nexus-value-trust-001 | 45.7613 | 36.5655 | 36.5651 | yes | 47368 |
| nexus-value-trust-002 | 75.0734 | 65.7505 | 65.7502 | yes | 54028 |

## Lesson

DCI is useful for evidence localization, but it must be lane-scoped. It is not the current route-cost fix. The immediate cost lever is reducing unnecessary R-phase model work through auto/lite admission, supervised bare-first, and payload/iteration caps while preserving claim and delivery gates.

The lesson was written to `.nexus/reports/learn/phase_writeback.jsonl` with topic `flash_hot4_dci_rtiming_p21_route_cost_regression`.

## Residual Debt

- Run auto/lite hot4 instead of forced Hyper to validate whether runtime route policy can skip expensive R-phase work.
- Add a hard route-cost gate that fails when with_nexus equals bare on verified rate but exceeds a configured cost ratio without extra trust/evidence value.
- Run Pro hot4 after the auto/lite change, not before.
