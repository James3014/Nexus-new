# Nexus Feature Reflex P68 Flash 3-Task Closure

Date: 2026-05-13

## Target

Make Gemini 3 Flash wearing Nexus preserve verified delivery and trust safety while removing the long-standing R/hyper wall-time cost for the public feature lane.

## Context+ Topology Verdict

- Hot path before P68: `model-required-feature-001` used `evidence_standard` and forced `hyper_sprint`, producing a prior feature `phase_wall_r_sec` of 38.3923s.
- Surgical seam: route-cost policy rule `feature:rlm-evidence-hard-neutral-direct-hyper` now maps public feature tasks to `feature_reflex`.
- New invariant: feature reflex must keep artifact/claim/delivery governance and require GWT plus hidden-verifier evidence before bypassing Hyper.

## Implementation

- Added `gwt_verification_artifact` emission for successful supervised public feature routes.
- Allowed deterministic pre-rescue admission for the new `feature_reflex` route lane.
- Changed the feature policy from `evidence_standard` to `feature_reflex`, with supervised bare-first and one bounded candidate.
- Added regression coverage proving feature reflex does not invoke Hyper when the supervised attempt is already verified.

## Verification Evidence

Command:

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py::test_feature_reflex_uses_supervised_bare_first_with_gwt_artifact tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_can_supervise_medium_risk_when_policy_explicitly_allows tests/benchmark/test_capability_ab_runner.py::test_context_sync_capped_uses_hidden_verified_deterministic_pre_rescue -q
```

Result: `3 passed in 1.55s`

Command:

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/engine/test_capability_planner.py -q
```

Result: `272 passed in 6.53s`

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001,model-required-feature-001,model-required-docs-001 \
  --output-dir .nexus/reports/p68_flash_model_required_feature_reflex_3task_1trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 1 \
  --timeout-sec 180 \
  --total-timeout-sec 900 \
  --stop-loss-sec 900 \
  --per-task-stop-loss-sec 240 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Result:

- With Nexus: 3/3 semantic verified, trust mismatch 0.0, avg wall 68.1811s, avg tokens 65804.0, avg model calls 1.0.
- Bare: 1/3 semantic verified, trust mismatch 0.0, avg wall 104.1365s, avg tokens 66376.3333, avg model calls 1.0.
- Cost efficiency gate: `IMPROVED`.
- Public delivery claim gate: `PASS`.
- Public cost safety gate: `PASS`.
- Prompt purity index max: 1.0.
- R/hyper wall: avg `phase_wall_r_sec` 0.0, avg `r_phase_hyper_sprint_sec` 0.0.

Feature row:

- `runtime_classification`: `nexus_supervised_bare_first`
- `route_cost_policy_lane`: `feature_reflex`
- `feature_reflex_route`: true
- `gwt_artifact_present`: true
- `gwt_semantic_hit_rate`: 1.0
- `deterministic_outcome_signature`: `single_file_feature_verified_by_gwt`
- `phase_wall_r_sec`: null
- `r_phase_hyper_sprint_sec`: null

## Acceptance Gate Verdict

PASS for this slice.

Evidence:

- Code artifacts: `scripts/bench/capability_ab_runner.py`, `.nexus/policy/promoted_route_cost_policy.json`
- Test artifacts: `tests/benchmark/test_capability_ab_runner.py`
- Command artifacts: P68 evidence bundle and JSONL rows under `.nexus/reports/p68_flash_model_required_feature_reflex_3task_1trial/`

## Residual Debt

- Markdown report still prints the legacy `Public claim gate: FAIL` section, while `evidence_bundle.json` has the split gates as `PASS` / `IMPROVED`. This is a report-rendering contract mismatch, not a route failure.
- `clean_model_cost_evidence_rate` is 0.3333 because repair/docs deterministic pre-rescue rows are classified as `rescue_only_local_success`. This is acceptable for delivery/cost gates but not yet ideal for training-export eligibility.
- Capability coverage table still reports several capabilities as `legacy` or `legacy_untrusted` in the markdown view; the next slice should align the report surface with the newer split claim posture.

## Next Plan

Final goal: Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approaches GPT-5.5 direct verified delivery on fixed public tasks while preserving trust mismatch 0 and making always-on cost defensible.

P69. Fix markdown claim-posture rendering so the human report reads the same split gates as `evidence_bundle.json`: delivery, cost safety, and cost efficiency.

P70. Add tests that fail if markdown says `Public claim gate: FAIL` when `evidence_bundle.public_claim_gate.verdict == PASS`.

P71. Add a `feature_reflex_route` summary table to the markdown report with GWT artifact status, semantic hit rate, and Hyper bypass evidence.

P72. Split `clean_model_cost_evidence` from `training_eligible_cost_evidence` so deterministic rescue rows can remain public-safe while being excluded or specially labeled for training export.

P73. Add a training-export gate requiring GWT artifact, hidden verifier pass, provider token measured, and no report-posture contradiction.

P74. Run Flash 3-task x3 for repair/feature/docs with hidden verifier, fail fast on any trust mismatch or delivery regression.

P75. If Flash x3 passes, run Pro 3-task x1 only as a sanity check, not as the main optimization loop.

P76. Write a consolidated public-candidate closure report with explicit limitation: this proves a 3-task lane slice, not broad production generalization.
