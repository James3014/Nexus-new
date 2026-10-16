# Nexus Feature Reflex P80b Flash 3-Task x3 Closure

## Goal

Keep Gemini 3 Flash wearing Nexus verified and trust-safe on the fixed model-required repair/feature/docs public slice while making the telemetry/cost evidence public-safe. Do not expand to Pro until Flash has a complete same-model denominator and cost gates no longer fail due instrumentation.

## Context+ Topology

The active hot path moved twice:

1. Before P68: feature/evidence-standard tasks opened R/hyper unnecessarily.
2. Before P80: Gemini token stats outliers hid cost lineage and caused public cost-safety failure.
3. After P80b: R/hyper remains zero, delivery and cost-safety pass, and the remaining blocker is true token efficiency rather than telemetry ambiguity.

## P80b Evidence

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001,model-required-feature-001,model-required-docs-001 \
  --output-dir .nexus/reports/p80b_flash_model_required_feature_reflex_3task_3trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 3 \
  --timeout-sec 240 \
  --total-timeout-sec 2700 \
  --stop-loss-sec 2700 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Result:

- with Nexus: 9/9 eligible, semantic verified rate 1.0.
- bare: 9/9 eligible, semantic verified rate 0.4444.
- trust mismatch: 0.0.
- public claim gate: PASS.
- verified delivery claim gate: PASS.
- public cost-safety gate: PASS.
- public cost-efficiency gate: REGRESSED.
- allowed public wording: `verified_delivery_uplift`.

Cost and telemetry:

- with Nexus avg wall: 54.0056s.
- bare avg wall: 57.4371s.
- wall ratio: 0.9403x.
- median paired wall ratio: 0.821x.
- with Nexus avg tokens: 63690.8889.
- bare avg tokens: 55915.0.
- token ratio: 1.1391x.
- median paired token ratio: 1.0051x.
- with Nexus token measured rate: 1.0.
- with Nexus provider token measured rate: 1.0.
- bare token measured rate: 0.8889, with one row transparently marked `estimated_from_stats_outlier`.

## Acceptance Evidence Gate

Verdict: PASS for delivery, trust, R/hyper suppression, denominator completeness, and public cost-safety. RETURN for final cost-efficiency target because token cost is not improved.

Reasons:

- PASS: same-model denominator is complete, 9/9 per arm.
- PASS: with Nexus verified delivery is 1.0 versus bare 0.4444.
- PASS: trust mismatch is 0.
- PASS: R/hyper remains zero for the Flash 3-task x3 slice.
- PASS: Nexus-side token telemetry is measured and public-safe.
- RETURN: token cost is not improved; `public_cost_efficiency_claim_gate=REGRESSED` with `token_cost_not_improved`.

## Failure Lesson

Do not treat provider stats parse failures as infra-invalid when the model call returned usable token telemetry. Bare model malformed output is a valid model failure, not a denominator failure, if invocation happened and tokens were observed. Also, do not convert cumulative-looking Gemini stats into measured tokens; preserve raw provider lineage and fail closed on efficiency wording.

## Next Long Plan

Final target: Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approaches GPT-5.5 direct verified delivery on fixed public tasks, with trust mismatch 0, public-safe telemetry, and defensible always-on cost.

Current target: reduce the remaining Flash token overhead without weakening verified delivery, trust safety, or R/hyper suppression.

P81. Token payload attribution: add per-row `first_call_prompt_chars`, `task_contract_chars`, `nexus_control_chars`, and `candidate_payload_chars` for supervised bare-first / feature-reflex / context-sync lanes.

P82. Token delta report: compute paired token deltas by task and lane, separating repair, feature, docs, and local deterministic pre-rescue rows.

P83. Prompt compaction gate: enforce lane-specific maximum control payload for Flash first call while preserving hidden verifier and governance receipts.

P84. Re-run Flash 3-task x3. Proceed only if delivery PASS, trust 0, R/hyper 0, cost-safety PASS, and token ratio is <= 1.05 or reason-coded as acceptable governance overhead.

P85. If Flash token ratio remains > 1.05, inspect exact payload segments before any route change. Do not remove Artifact/Claim/Delivery gates.

P86. Once Flash passes P84, run Pro x1 sanity for the same slice.

P87. Produce consolidated public posture report with separate delivery, cost-safety, and cost-efficiency claims.

P88. Export only evidence-safe rows to training/Autodata: evidence bundle, same-model before/after, hidden verifier, public-safe cost telemetry, and route/prompt delta must be present.
