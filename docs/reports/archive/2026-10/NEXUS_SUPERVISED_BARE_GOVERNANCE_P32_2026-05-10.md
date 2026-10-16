# Nexus Supervised Bare Governance P32 Closure

Date: 2026-05-10

## Decision

`supervised_bare_first` is allowed only as a supervised proposal path, not as trusted delivery.

The safe contract is:

1. the weak model proposes first;
2. Nexus requires hidden verifier mode before accepting supervised bare-first;
3. Nexus records route, context, claim, and model-use receipts;
4. hidden verifier failure triggers bounded retry/rescue instead of accepting the visible pass;
5. strict public runs cannot bypass model involvement through policy `skip_llm_baseline`.

This keeps governance active while reducing unnecessary full-armor work. Bare output is never the final authority.

## Implemented Guardrails

- `supervised_bare_first` now requires `NEXUS_VALUE_HIDDEN_VERIFIER=1`.
- Strict same-model benchmark runs override promoted policy `skip_llm_baseline`.
- Hidden verifier failures trigger bounded retry in strict, lite, and supervised routes when a model attempt happened.
- Successful supervised bare-first rows emit hidden-verifier, route-decision, claim, and context-delivery receipts.
- Strict model failures can fall back to bounded Nexus rescue and are annotated as rescue, not bare success.

## Flash Evidence

Run: `.nexus/reports/flash_8x1_public_value_strict_p28/evidence_bundle.json`

- Public claim gate: PASS.
- Same model / same tasks: true.
- Hidden verifier mode: true.
- With Nexus semantic verified: 8/8.
- Bare semantic verified: 6/8.
- Trust mismatch: 0.0 / 0.0.
- Model uses Nexus rate: 1.0.
- Nexus context delivered rate: 1.0.
- Claim verified rate: 1.0.
- Token ratio: 1.0278x.
- Wall ratio: 2.3583x.

Interpretation: Flash governance and correctness are now acceptable; cost is not yet closure-grade because hidden retry/rescue still makes wall time high.

## Pro Evidence

Run: `.nexus/reports/pro_hot4_auto_cost_gate_p29/evidence_bundle.json`

- Public claim gate: PASS.
- Same model / same tasks: true.
- Hidden verifier mode: true.
- With Nexus semantic verified: 4/4.
- Bare semantic verified: 2/4.
- Trust mismatch: 0.0 / 0.0.
- Model uses Nexus rate: 1.0.
- Nexus context delivered rate: 1.0.
- Claim verified rate: 1.0.
- Token ratio: 1.0041x.
- Wall ratio: 1.3280x.

Interpretation: Pro hot4 is in the intended zone: Nexus improves verified delivery with nearly flat token cost and acceptable wall overhead.

## Residual Debt

- Flash 8x1 still has high wall overhead, mostly from Phase R and hidden retry/rescue paths.
- Provider token measured rate in Flash strict 8x1 is 0.875, above the current gate but still below ideal.
- The next route-cost work should target lane-specific wall trimming, not weaken hidden verifier or claim gates.

## Next Gate

Do not relax governance gates. The next acceptable optimization is:

- keep hidden verifier required;
- keep trust mismatch at 0;
- keep model-use and context-delivery rates at 1.0;
- reduce Flash wall ratio toward <= 1.8x using phase-wall and hidden-retry slimming.
