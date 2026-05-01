# Nexus Routing v5 Execution Plan

## What

This plan reconciles two route-optimization inputs:

- `docs/reports/NEXUS_ROUTE_ADJUSTMENT_PLAN_2026-05-01.md`
- `/Users/jameschen/Workspace/nexus/docs/reports/RFC-OPT-001_NEXUS_ROUTING_V5.md`

The chosen direction is conservative: keep `CapabilityPlanner` as the single routing authority, restore auto-routing in public benchmarks, and introduce Routing v5 as an observable tier signal before it changes executor behavior.

## Why

The current evidence says Nexus already improves verified delivery across three models, but cost behavior differs by model. The next optimization should reduce unnecessary heavy-path usage without weakening governance.

The RFC direction is useful, but it cannot be applied directly yet because:

- RFC risk thresholds use `0.0-1.0`; current route signals use `0-100`.
- Policy pruning needs `impact_scope` or `GLOBAL` metadata before it is safe.
- Forecast early exit must not skip artifact, claim, or delivery gates.
- `AutonomicRouter` must not become a second authority for capability selection.

## How

### P1. Restore Auto-Routing In Public Benchmarks

- Remove `--force-flow hyper_sprint` from public value comparison paths.
- Keep stress lanes separate when forcing Hyper.
- Preserve route metadata for every row.

Acceptance:

- Public benchmark commands document whether they use `auto` or stress force-flow.
- Reports include route recommendation, chosen flow, and capability stack.

### P2. Add Route Cost Ledger Gate

- Add a top-level `route_cost_ledger` section to benchmark evidence bundles.
- Track available measured telemetry:
  - wall duration
  - model calls
  - measured tokens
  - route recommendation
  - chosen flow
  - capability selected/invoked/evidence counts
  - token reliability

Acceptance:

- Final multi-model report can fail if route cost ledger is absent when cost claims are enabled.
- Report wording stays scoped to measured telemetry, not billing cost.

### P3. Define Risk Normalization Contract

- Add explicit fields:
  - `risk_score_0_100`
  - `risk_score_0_1`
  - `risk_band`: `green_lane | hardened | deep`
  - `risk_band_reason`

Acceptance:

- No direct use of RFC thresholds without normalization.
- Existing route behavior remains unchanged in shadow mode.

### P4. Introduce Routing v5 Shadow Signal

- Add a planner-level suggested tier:
  - Green-Lane: low risk, low ambiguity, non-core, verified memory optional.
  - Hardened: medium risk, evidence/governance needed.
  - Deep: core/engine/security/cross-module or repeated failure.

Acceptance:

- `CapabilityPlanner` emits the suggested tier.
- `AutonomicRouter` remains diagnostic only.
- No executor behavior changes yet.

### P5. Add Core/Engine Governance Lock

- Treat these as minimum Hardened:
  - `nexus/core/`
  - `nexus/engine/`
  - `scripts/ops/`
  - security/governance/state-contract paths

- Treat cross-module core contract changes as Deep.

Acceptance:

- Tests prove budget downgrade cannot remove required gates for locked paths.

### P6. Prepare Safe Policy Pruning Metadata

- Add policy metadata concept:
  - `impact_scope`
  - `GLOBAL`
  - `security`
  - `governance`
  - `core_contract`

Acceptance:

- Unknown scope defaults to include.
- GLOBAL/security/governance policies are never pruned.

### P7. Forecast-Gate Early Exit In Shadow Mode

- Only suggest skipping Research when:
  - risk is Green-Lane
  - task is non-core
  - confidence is high
  - memory evidence is verified
  - artifact/claim/delivery gates remain active

Acceptance:

- Shadow report tracks false-negative candidates.
- No production route skips Research until observation data passes.

### P8. Promotion Criteria

Routing v5 can become active only when:

- verified delivery does not regress
- public claim gate remains PASS
- trust mismatch remains 0
- route cost ledger is complete
- wall time or token telemetry improves on at least one model without hurting the others

## Current Public Evidence Baseline

Frozen execution-safe benchmark, 12 tasks x 2 trials:

| Model | Bare verified | Nexus verified | Lift |
| :--- | ---: | ---: | ---: |
| Gemini 3 Flash | 58.3% | 100.0% | +41.7pp |
| Gemini 3.1 Pro | 45.8% | 100.0% | +54.2pp |
| GPT-5.5 | 58.3% | 100.0% | +41.7pp |

This baseline should be treated as the pre-v5 promotion reference.

## Residual Debt

- Cost telemetry is measured benchmark telemetry, not billing cost.
- GPT-5.5 currently has public-safe evidence for `codeintel`; Gemini reports also public-safe `autoreason` and `ultra_review`.
- Route cost ledger completeness is not yet part of the final multi-model gate.
