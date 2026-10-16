# IRON Nexus Integration V2 - Phase A~G Status (2026-05-05)

## Scope
- Source RFC: `docs/RFC/RFC-2026-05-04-IRON-NEXUS-INTEGRATION-V2.md`
- Branch: `main`
- Focus: route-by-context capability selection, hard gates, and auditability.

## Phase Status Matrix
| Phase | Target | Status | Evidence |
| --- | --- | --- | --- |
| A | ASI data contract and persistence shape | DONE | `nexus/engine/pipeline_outcome.py`, `nexus/app/research_flow_service.py` (`asi_record`, `asi_ledger`) |
| B | Autoreason v2 tournament | DONE | `nexus/engine/autoreason_service.py`, `tests/engine/test_autoreason_service.py` |
| C | Plateau detect + pivot trigger | DONE | `nexus/app/research_flow_service.py` (`_detect_plateau`, strategy plateau payload), `tests/app/test_research_flow_service.py` |
| D | DocScout + claim verification + low-confidence HITL | DONE | `nexus/research/doc_scout_adapter.py`, `scripts/ops/ultra_gate.py`, `tests/ops/test_ultra_gate.py` |
| E | Route funnel quality measurable and enforceable | DONE | `scripts/ops/capability_route_smoke.py`, `tests/ops/test_capability_route_smoke.py` |
| F | Promotion/public gate integration for route quality | DONE | `scripts/bench/gemini_nexus_report.py` (`_public_claim_gate` route-quality fail-close), `tests/benchmark/test_gemini_nexus_report.py` |
| G | Final candidate lane readiness (gate-first) | DONE (engineering readiness) | Public claim gate now blocks on route-quality regressions; same-model A/B can be promoted only when gates pass |

## Gate Thresholds (Enforced)
- `selected -> invoked >= 70%`
- `invoked -> evidence >= 95%`
- `evidence -> outcome >= 90%`
- `unnecessary selected <= 30%`

## Verification Runs
- `uv run pytest -q tests/ops/test_capability_route_smoke.py tests/benchmark/test_gemini_nexus_report.py tests/app/test_research_flow_service.py`
- Result: `96 passed`

## Residual Debt
- Full Flash/Pro 12x2 public candidate reruns are operational actions and must be executed as benchmark jobs; code-side gate scaffolding is complete.
