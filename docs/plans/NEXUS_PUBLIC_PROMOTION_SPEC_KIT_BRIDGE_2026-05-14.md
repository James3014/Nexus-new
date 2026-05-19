# Nexus Public Promotion Spec Bridge

## Goal

Gemini 3 Flash / Gemini 3.1 Pro through Nexus should approach GPT-5.5 direct verified delivery on a fixed public taskset, with trust mismatch 0, replayable evidence, and always-on cost that is public-claim safe.

## Current Evidence

- Flash + Nexus: promotion-ready on the fixed sanitized 12-task public smoke.
  - Evidence bundle: `/private/tmp/nexus-sanitized-runner-flash-full2-20260514/reports/evidence_bundle.json`
  - `public_promotion_readiness_contract=PASS`
  - `route_policy_evidence_contract=PASS`
  - `public_verified_delivery_claim_gate=PASS`
  - `public_cost_efficiency_claim_gate=IMPROVED`
  - `x3_promotion_gate=PASS`
- Gemini 3.1 Pro + Nexus: promotion-ready after direct-arm refill for provider evidence gaps.
  - Evidence bundle: `/private/tmp/nexus-sanitized-runner-pro-hook4-20260514/reports/refilled_public4_20260515/evidence_bundle.json`
  - `public_promotion_readiness_contract=PASS`
  - `route_policy_evidence_contract=PASS`
  - `public_verified_delivery_claim_gate=PASS`
  - `public_cost_efficiency_claim_gate=IMPROVED`
  - `x3_promotion_gate=PASS`
- GPT-5.5 direct: baseline/reference only for the current dashboard.
- GPT-5.5 + Nexus hook10: observation-only; do not use for parity or external public-model claims.
  - Evidence bundle: `/private/tmp/nexus-sanitized-runner-gpt55-hook10-20260515/reports/evidence_bundle.json`
  - Fixed since hook5: outbound prompt ledger forbidden literals cleared, trust-row receipt contracts pass, session worker contamination is 0, model annotation is same-model, route-policy evidence passes, provider-token telemetry is complete, wall-ledger telemetry is conserved on both arms, and Codex Nexus control-plane prompt attribution clears prompt-purity.
  - Current gate state: `public_claim_gate=PASS`, `public_verified_delivery_claim_gate=PASS`, `public_cost_claim_gate=PASS`, `public_cost_efficiency_claim_gate=IMPROVED`, and `trust_mismatch_rate=0`.
  - Remaining blocker: Codex prompt-wearing-only provider boundary keeps the full `public_promotion_readiness_contract=RETURN`; x3 readiness is not established for this observation-only lane.
- Trust mismatch: 0 for promotion-ready Flash and Pro bundles.
- Gap dashboard: `/private/tmp/nexus-public-gap-dashboard-20260515-flash-pro-ready-gpt55-hook10-observation.json`
  - Dashboard separates smoke promotion from final goal readiness: Flash/Pro remain `promotion_ready=true` for the fixed 12-task smoke, but `final_goal_ready=false` until the same gates pass on a compiled commercial benchmark lane bundle.

## Promotion State Contract

`promotion_state_contract_v1`:

| Lane | Status | Public wording allowed | Evidence boundary |
| --- | --- | --- | --- |
| Flash + Nexus | `PROMOTION_READY` | verified delivery, trust=0, cost efficiency improved | fixed 12-task sanitized public smoke |
| Pro + Nexus | `PROMOTION_READY` | verified delivery, trust=0, cost efficiency improved after refill disclosure | fixed 12-task sanitized public smoke plus direct-arm provider-evidence refill |
| GPT-5.5 direct | `BASELINE_REFERENCE` | direct verified baseline only | no Nexus uplift claim |
| GPT-5.5 + Nexus | `OBSERVATION_ONLY` | hook10 provider-boundary analysis only | no external public-model or parity claim |
| Spec Kit | `INSTALLED_CONTRACT_TOOL` | contract shaping only | `.specify` init disallowed while repo is dirty |

Final-goal readiness additionally requires `benchmark_basis_contract.commercial_model_basis_ready=true`; smoke promotion alone is not enough for the final Gemini Flash/Pro versus GPT-5.5 direct claim.

Refill disclosure is required whenever a public bundle replaces infra-invalid or provider-token-unmeasured rows. Refill may repair evidence completeness, but it must not synthesize semantic success.

## Spec Boundary

- Delivery, trust, replay, and cost claims stay separate.
- `required` capability protection must not be bypassed by local rescue.
- `cost_capped` capability protection may use deterministic pre-model rescue only when:
  - hidden verifier is required and passes;
  - route policy explicitly enables pre-model deterministic rescue;
  - local reflex risk is low and bare sufficiency is high;
  - row evidence records `route_execution_policy.reason_codes`;
  - wall/token/model-call ledgers remain conserved.
- Public promotion readiness must require `route_policy_evidence_pass`.
- Every public evidence bundle must emit `route_policy_evidence_contract` with schema
  `nexus_route_policy_evidence_contract_v1`.

## Route Policy Evidence Contract

`route_policy_evidence_contract` is a fail-closed bundle-level gate. It reads rows; it must not rerun
models, rewrite row verdicts, or synthesize missing route evidence.

Required checks:

- Every eligible with-Nexus public row has `route_execution_policy`.
- `route_execution_policy.reason_codes` is present and is a list.
- `cost_capped_capability_allows_verified_pre_model_rescue` is only public-eligible when:
  - `capability_activation_contract=cost_capped`;
  - `hidden_verifier_passed=true`;
  - `local_reflex_risk_level=low`;
  - `local_reflex_bare_sufficiency=high`;
  - `nexus_winner_source=local_deterministic_pre_model_rescue`.
- `required` protected-capability lanes must never allow pre-model deterministic rescue.

Failure taxonomy:

- `route_execution_policy_missing`
- `route_execution_policy_reason_codes_missing`
- `cost_capped_rescue_without_cost_capped_contract`
- `cost_capped_rescue_without_hidden_verifier_pass`
- `cost_capped_rescue_without_low_risk`
- `cost_capped_rescue_without_high_bare_sufficiency`
- `cost_capped_rescue_without_deterministic_delivery_source`
- `required_protected_capability_pre_model_rescue_allowed`

## Implementation Tasks

1. Extract route execution decisions into a small policy module with explicit reason codes.
2. Record route policy on every with-Nexus row used for public claims.
3. Permit verified pre-model deterministic rescue for `cost_capped` repair lanes without weakening `required` lanes.
4. Keep sanitized runner and clean runner dependency closure synchronized before live smoke.
5. Add `route_policy_evidence_contract` to evidence bundles before public claim gates are built.
6. Rerun Flash repair-only, then full Flash 12-task smoke.
7. Promote only if public delivery, route-policy evidence, trust, replay, warning, token, wall-ledger, outbound-ledger, x3, and non-regressed cost efficiency all pass.

## Non-Goals

- Do not install community Spec Kit extensions for this benchmark lane.
- Do not initialize `.specify` in the dirty Nexus worktree during this slice.
- Do not claim GPT-5.5 parity until GPT-5.5 direct and Nexus arms are run under the same fixed harness with a non prompt-wearing-only public-safe provider boundary.
