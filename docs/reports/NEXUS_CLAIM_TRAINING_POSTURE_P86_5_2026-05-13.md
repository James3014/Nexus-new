# Nexus P86.5 Claim and Training Posture Hardening

## Goal

Lock the docs-lane public wording and training eligibility contracts after P86 made `model-required-docs-001` audit-complete. The target is not a prettier single-task number; the target is preventing single-pair evidence from being misread as statistically sufficient cost improvement.

## Changes

- Added machine-readable public wording posture to `scripts/bench/capability_ab_runner.py`.
- Added `cost_efficiency_wording_allowed`, `public_wording_key`, and `public_wording_allowed`.
- Added `training_eligibility_posture` with `TRAINING_ELIGIBLE` vs `OBSERVATION_ONLY`.
- Made sample insufficiency dominate public wording: `sample_sufficient=false` can only produce `promising_but_insufficient_sample` for a delivery-safe bundle.
- Added P86.5 mutation-style hard cases:
  - Receipts complete but provider token telemetry missing returns via cost rubric.
  - Provider token telemetry complete but one required receipt missing returns via evidence rubric.

## Evidence

### Unit and regression

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py::test_rubric_returns_when_receipts_pass_but_provider_tokens_missing tests/benchmark/test_capability_ab_runner.py::test_rubric_returns_when_provider_tokens_pass_but_required_receipt_missing tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q
4 passed
```

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q
369 passed
```

### Live replay

Path: `.nexus/reports/p86_5_claim_training_posture_docs_1trial_b/evidence_bundle.json`

The live rerun was deliberately fail-closed because the bare arm timed out before a model call:

```json
{
  "delivery": "FAIL",
  "cost_safety": "FAIL",
  "wording_key": "no_public_claim",
  "training_status": "OBSERVATION_ONLY",
  "reason_codes": [
    "cost_safety_not_passed",
    "delivery_gate_not_passed",
    "sample_insufficient"
  ]
}
```

### Recomputed valid pair

Path: `.nexus/reports/p86_5_claim_training_posture_docs_1trial_recomputed/evidence_bundle.json`

This recomputed the previous valid P86 raw rows through the new bundle writer:

```json
{
  "delivery": "PASS",
  "cost_safety": "PASS",
  "cost_efficiency": "REGRESSED",
  "wall_ratio": 0.8701,
  "token_ratio": 1.0849,
  "sample_sufficient": false,
  "wording_key": "promising_but_insufficient_sample",
  "cost_wording_allowed": false,
  "training_status": "OBSERVATION_ONLY",
  "training_reasons": ["sample_insufficient"],
  "rubric_overall_pass_rate": 1.0
}
```

## Verdict

P86.5 is PASS for contract hardening.

It is not a public cost-improvement claim. The correct posture is `OBSERVATION_ONLY` until at least three valid pairs satisfy the sampling gate and the wall ledger is conserved.

## Residual Debt

- P87 must add wall-ledger conservation fields: `unattributed_wall_sec`, `wall_ledger_reconciliation_error_ratio`, and `wall_ledger_conserved`.
- P88/P89 must stratify docs tasks into pure docs, docs-code sync, and evidence-citation docs before any public cost wording can be promoted.
- Live Gemini runs still emit `<unknown>:270: SyntaxWarning: 'return' in a 'finally' block`; this is non-blocking but should be cleaned before broad benchmark publication.

## P86.6 Addendum

P86.6 added infra-invalid quarantine and stricter public wording/training substatus.

### Additional Changes

- Added `infra_quarantine_report` to the evidence bundle.
- Added per-pair fields:
  - `infra_valid_pair`
  - `infra_invalid_reason_code`
  - `infra_invalid_reason_codes`
- Added training posture substatuses:
  - `OBSERVATION_ONLY_INFRA_INVALID`
  - `OBSERVATION_ONLY_SAMPLE_INSUFFICIENT`
- Updated Markdown claim posture rendering so sample-insufficient bundles show cost efficiency as `INCONCLUSIVE`.

### Additional Evidence

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q
369 passed
```

Recomputed valid-pair bundle:

Path: `.nexus/reports/p86_6_infra_quarantine_docs_1trial_recomputed/evidence_bundle.json`

```json
{
  "delivery": "PASS",
  "cost_safety": "PASS",
  "cost_efficiency": "REGRESSED",
  "infra_valid_pair_count": 1,
  "infra_invalid_pair_count": 0,
  "wording_key": "promising_but_insufficient_sample",
  "cost_wording_allowed": false,
  "training_status": "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
}
```

Markdown posture scan:

```text
Cost efficiency: INCONCLUSIVE
banned_found=[]
```

## P86.7 Addendum

P86.7 performed a zero-semantics structural seam refactor before P87 wall-ledger work.

### Refactor

- Extracted `compute_infra_quarantine_report(...)`.
- Extracted `derive_public_claim_posture(...)`.
- Extracted `derive_training_eligibility_posture(...)`.

The goal is locality: P87 can add wall-ledger conservation inside an evaluator seam instead of expanding `write_evidence_bundle(...)`.

### Evidence

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q
3 passed
```

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
216 passed
```

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q
369 passed
```

Recomputed valid-pair bundle:

Path: `.nexus/reports/p86_7_evaluator_seam_docs_1trial_recomputed/evidence_bundle.json`

```json
{
  "delivery": "PASS",
  "cost_safety": "PASS",
  "cost_efficiency": "REGRESSED",
  "infra_valid_pair_count": 1,
  "wording_key": "promising_but_insufficient_sample",
  "training": "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
}
```

### Verdict

P86.7 is PASS for structural soundness. It intentionally does not claim new benchmark performance.

## P87 Addendum

P87 added wall-ledger conservation as a separate evaluator instead of extending claim assembly inline.

### Changes

- Added `evaluate_wall_ledger_conservation(...)`.
- Added `summarize_wall_ledger_conservation(...)`.
- Added bundle-level `wall_ledger_conservation`.
- Added row fields:
  - `wall_ledger_status`
  - `wall_ledger_component_coverage_rate`
  - `unattributed_wall_sec`
  - `max_component_drift_sec`
  - `wall_ledger_reconciliation_error_ratio`
  - `wall_ledger_conserved`
- Connected wall-ledger invalid rows to:
  - `public_cost_efficiency_claim_gate = RETURN`
  - `training_eligibility_posture = OBSERVATION_ONLY_TELEMETRY_INVALID`

### Conservation Boundary

`receipt_elapsed_sec` is intentionally excluded from row-level wall conservation because it is a wrapper-span measurement and overlaps provider/model time in existing docs rows. The ledger only sums mutually attributable components such as gateway/model, hidden verifier, hidden retry, deterministic pre-rescue, and explicit `receipt_write_sec`.

### Evidence

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "wall_ledger or separates_delivery_lift_from_cost_efficiency_regression or write_trial_evidence_and_bundle"
6 passed
```

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
220 passed
```

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q
373 passed
```

Recomputed valid-pair bundle:

Path: `.nexus/reports/p87_wall_ledger_docs_1trial_recomputed/evidence_bundle.json`

```json
{
  "delivery": "PASS",
  "cost_safety": "PASS",
  "cost_efficiency": "REGRESSED",
  "wall_invalid": false,
  "with_nexus_conserved_rate": 1.0,
  "without_nexus_conserved_rate": 1.0,
  "with_nexus_reconciliation_error_ratio_max": 0.0056,
  "without_nexus_reconciliation_error_ratio_max": 0.005,
  "wording_key": "promising_but_insufficient_sample",
  "training": "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
}
```

### Verdict

P87 is PASS for telemetry conservation. It does not claim cost efficiency completion because the sample remains insufficient and the recomputed bundle still reports cost efficiency as `REGRESSED`.

## P88-P90 Addendum - Docs Lane Live Contract Hardening

### Objective
Stabilize the docs lane before broader P90/P94 expansion: remove ambiguous finally control flow, freeze a stratified docs manifest, quarantine infra-invalid pairs, and prove that one live docs pair can pass receipt/rubric/token contracts without weakening delivery gates.

### Changes
- P88 refactored baseline apply/probe cleanup in `nexus/app/research_flow_service.py` to a single restore helper, removing finally-embedded control-flow ambiguity.
- P88 added SyntaxWarning guards in both `nexus/research/sprint_service.py` and the direct provider patch seam in `scripts/bench/capability_ab_runner.py`.
- P89 added frozen docs-lane manifest `scripts/bench/public_benchmark_docs_lane_v1.json` with three strata and manifest-hashable task contracts.
- P90 fixed expected receipt backfill so unsafe/stale receipts no longer block public-safe receipt repair.

### Live Evidence
- `p90_1_docs_lane_public_field_smoke`: with_nexus eligible and measured, but without_nexus was infra-invalid (`quota_exhausted`), so the pair was quarantined and not usable for cost claims.
- `p90_2_docs_lane_public_field_smoke`: one valid pair, delivery PASS, cost safety PASS, public claim PASS, cost efficiency NEUTRAL, infra valid pair count 1, provider token measured rate 1.0, receipt/rubric contracts PASS, PPI 1.0.
- The live command still emitted `<unknown>:270: SyntaxWarning: 'return' in a 'finally' block` to process output even though row-level warning fields were empty and local AST scans found no finally-control-flow in `nexus/` or `scripts/`. This remains a public-candidate blocker-lite until captured or eliminated.

### Gate Posture
- PASS: docs single-pair contract integrity is now real for the public-field stratum.
- PASS: infra quarantine correctly excludes invalid pairs from cost denominators.
- RETURN: P90 full 3-task x1 is not yet rerun after the final warning guard because live warning cleanliness is still not proven.
- RETURN: sample sufficiency remains false; training posture stays observation-only.

### Next Required Cut
Before P90 full 3-task x1, capture live stderr warnings into row/bundle telemetry or eliminate the `<unknown>:270` emitter. Then run frozen manifest preflight, 3-task x1, and only expand to x3 if all strata remain eligible with trust mismatch 0.

### P90.3 Follow-up
A second single-task live smoke after adding deterministic pre-rescue compile guards still emitted `<unknown>:270: SyntaxWarning: 'return' in a 'finally' block` to process output. The row itself remained eligible and contract-clean: delivery PASS, cost safety PASS, public claim PASS, provider token measured rate 1.0, receipt/rubric contracts PASS, infra valid pair count 1, PPI 1.0. Cost efficiency changed to REGRESSED for that single pair and sample sufficiency remains false.

Interpretation: the docs lane contract is now usable for one public-field sample, but warning cleanliness is not yet an observable row/bundle contract. P90 full 3-task x1 should wait until live stderr warning capture is attached to row telemetry or the emitter is eliminated.

## P91-P93 Addendum - Warning Ledger Contract

### Objective
Make warning cleanliness machine-observable before expanding docs lane from single-task smoke to frozen 3-task batches.

### Changes
- Added `scripts/bench/warning_ledger.py` as a narrow warning telemetry module.
- Added row-level warning fields: `warning_clean`, `warning_capture_status`, `warning_capture_complete`, `warning_lines`, `warning_sources`, `warning_categories`, `warning_reason_codes`, and `uncaptured_warning_count`.
- Added `warning_clean_gate` to the evidence bundle. When `warning_ledger_required=true`, warning rows or missing warning capture force RETURN.
- Added docs-lane `stratum_type` fields: `pure_docs`, `docs_code_sync`, `evidence_required_docs`.

### Live Evidence
- `p93_warning_ledger_public_field_smoke`: warning capture worked. The previously hidden `<unknown>:270: SyntaxWarning: 'return' in a 'finally' block` is now recorded in row telemetry and the bundle.
- `warning_capture_completeness=1.0`, `uncaptured_warning_count=0`, `warning_source=with_nexus_runtime`.
- `warning_clean=false`, therefore `warning_clean_gate=RETURN` and `public_cost_efficiency_claim_gate=RETURN`.

### Method Note
AutoTTS / Agentic Discovery for Test-Time Scaling supports this sequencing: first build a tractable, cheap-feedback control environment, then let later route/prompt/verifier policies optimize against that environment. For Nexus, the warning ledger, infra quarantine, and wall ledger are that control environment.

### Gate Posture
- PASS: warning is no longer an observability black hole.
- RETURN: warning is still present, so full P90 3-task x1 remains blocked.
- RETURN: without arm was `quota_exhausted`, so the P93 pair is infra-invalid and excluded from cost-efficiency denominators.

### Next Required Cut
Eliminate or explicitly classify the `with_nexus_runtime` SyntaxWarning source. Only after `warning_clean_gate=PASS` should the frozen docs lane run full 3-task x1.

## P94 Addendum - Warning Source Attribution Contract

### Objective
Turn warning cleanup from a hidden stderr symptom into an attributable, replayable contract before expanding the docs lane sample.

### Changes
- Extended `scripts/bench/warning_ledger.py` with structured warning attribution: `warning_records`, `warning_locations`, `warning_filenames`, `warning_linenos`, `warning_emitters`, `warning_source_resolved_rate`, and `unresolved_warning_count`.
- Tightened the evidence bundle so `warning_ledger_required=true` returns when warning metadata is unresolved, not only when a warning line exists.
- Identified the first emitter as `scripts/bench/capability_ab_runner.py::_string_literals()` via stdlib-frame filtering, then suppressed candidate-snippet `SyntaxWarning` locally inside that leak-audit helper.
- Re-ran live smoke and found a second emitter in `nexus/services/codeintel/graph_builder.py::imports_for`; fixed it by parsing CodeIntel scan inputs with local `SyntaxWarning` suppression and a real filename.
- Updated route-oracle schema expectations to match the existing 12-task route oracle manifest drift.

### Live Evidence
- `p94_warning_attribution_public_field_smoke`: warning attribution worked, but the first emitter was still a stdlib `ast.py` frame. The gate stayed RETURN.
- `p94_warning_clean_public_field_smoke`: attribution resolved the repo emitter as `nexus/services/codeintel/graph_builder.py:46:imports_for`. The gate stayed RETURN, proving the unresolved-source check was active.
- `p94_warning_clean_public_field_smoke_2`: `warning_clean_gate=PASS`, `warning_capture_completeness=1.0`, `warning_source_resolved_rate=1.0`, `unresolved_warning_count=0`.
- Same live smoke: delivery PASS, cost safety PASS, cost efficiency IMPROVED for the single pair, wall ratio 0.3302, token ratio 0.9775, trust mismatch 0, provider token measured rates 1.0/1.0.

### Verification
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "warning_ledger or python_syntax_warning or string_literals"` -> 5 passed.
- `uv run pytest tests/nexus/codeintel/test_graph_builder.py -q` -> 4 passed.
- `uv run python -m py_compile scripts/bench/warning_ledger.py scripts/bench/capability_ab_runner.py nexus/services/codeintel/graph_builder.py` -> PASS.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_capability_tasks_schema.py tests/nexus/codeintel/test_graph_builder.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q` -> 394 passed.

### Failure Lessons
- A captured warning is not enough; public-path warning telemetry must include repo-level emitter attribution, otherwise the system only has a cleaner black box.
- Candidate parse warnings from read-only analysis helpers must be suppressed at the helper seam, not globally. Global suppression would weaken the warning ledger.
- Broad tests exposed existing route-oracle manifest drift: the manifest had 12 tasks while the test still asserted 10. Schema tests must track frozen-manifest versioning, not stale counts.

### Gate Posture
- PASS: P94 warning source attribution contract is now active and clean for the single public-field docs smoke.
- PASS: docs single-pair delivery/cost-safety remains valid with trust mismatch 0.
- RETURN: sample sufficiency is still false, so training posture remains observation-only and public cost-improvement wording is not yet statistically claim-safe.

### Next Required Cut
Run frozen docs-lane 3-task x1 under the same warning/wall/receipt/rubric gates. Do not expand to x3 until all three strata are eligible, warning-clean, wall-ledger-conserved, and trust-mismatch-free.

## P95 Addendum - Preflight Sentinel

### Objective
Move the next likely blind spots in front of live 3-task runs. The sentinel must stop a batch before it enters the denominator when manifest strata, warning capture, wall conservation, infra quarantine, provider-token measurement, or hidden verifier contracts are not ready.

### Changes
- Added a `nexus_preflight_sentinel_v1` block to `build_public_benchmark_preflight(...)`.
- The sentinel emits a controller branch: `continue` or `stop`.
- The sentinel hard-checks manifest hash, warning ledger requirement, wall ledger requirement, infra quarantine requirement, provider token measurement requirement, hidden verifier state, and docs-lane strata coverage.
- For `nexus-public-docs-lane-v1`, full-batch preflight now requires the three strata: `pure_docs`, `docs_code_sync`, and `evidence_required_docs`.
- Updated manifest shape validation so `stratum_type` is a first-class allowed task field instead of an unknown-field failure.

### Live Evidence
- Initial P95 preflight found a validator drift: the docs manifest had valid `stratum_type` fields, but `_public_manifest_shape_failures(...)` still rejected them as unknown.
- After fixing the validator, `p95_preflight_sentinel_docs_x1_2` returned `status=PASS`.
- Same preflight: `preflight_sentinel.status=PASS`, `controller_policy.branch=continue`, selected task count 3, selected strata `docs_code_sync`, `evidence_required_docs`, `pure_docs`.
- Denominator policy is now explicit: exclude any pair with `infra_invalid`, warning-dirty telemetry, or invalid wall ledger.

### Verification
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "preflight_sentinel or public_benchmark_preflight_passes_without_model_invocation"` -> 2 passed.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_capability_tasks_schema.py tests/nexus/codeintel/test_graph_builder.py -q` -> 239 passed.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_capability_tasks_schema.py tests/nexus/codeintel/test_graph_builder.py tests/app/test_research_flow_service.py tests/research/test_sprint_service.py tests/services/test_gemini_cli.py -q` -> 395 passed.
- `uv run python -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/warning_ledger.py nexus/services/codeintel/graph_builder.py` -> PASS.

### Failure Lessons
- Adding a manifest field in schema is insufficient; shape validators must accept the same field, or preflight will fail before the sentinel can do useful control work.
- The preflight sentinel should stay cheap and non-generative. It should branch/stop before live execution, not repair live rows after denominator pollution.
- Worktree dirtiness should stay recorded as warning unless `require_clean_worktree=true`; otherwise existing dirty unrelated work would block local iteration.

### Gate Posture
- PASS: P95 preflight sentinel is active for docs-lane x1/x3 entry.
- PASS: frozen docs 3-task x1 is now allowed to proceed.
- RETURN: public cost-improvement wording still waits for 3-task x1/x3 evidence, not this preflight.

### Next Required Cut
Run the frozen docs-lane 3-task x1. Accept only rows that are warning-clean, wall-ledger-conserved, provider-token-measured, infra-valid, receipt/rubric complete, and trust-mismatch-free.

## P96 Addendum - Docs Lane 3-Task x1 Live

### Objective
Run the frozen docs-lane 3-strata x1 live after the P95 sentinel passed. Keep delivery, cost safety, cost efficiency, and training eligibility separated.

### P96 preflight insurance
- `preflight_sentinel.status=PASS`.
- `controller_policy.branch=continue`.
- Selected strata: `docs_code_sync`, `evidence_required_docs`, `pure_docs`.
- Added explicit stop conditions for warning-dirty, infra-invalid, wall-invalid, provider-token-missing, and receipt/rubric RETURN rows.
- Added DCI-style raw warning pointer metadata through `WarningRecord.emitter=raw_stream:<offset>:<sha256>`.
- Added ACH canary coverage declarations for missing stratum, warning dirty, wall invalid, and provider-token missing.

### Live result
- P96 report: `.nexus/reports/p96_docs_lane_3task_x1_live/evidence_bundle.json`.
- With Nexus: 3/3 eligible, 3/3 semantic verified, trust mismatch 0.
- Without Nexus: 3/3 eligible, 1/3 semantic verified, trust mismatch 0.
- `public_delivery_gate=PASS`.
- `public_cost_claim_gate=PASS`.
- `public_cost_efficiency_claim_gate=REGRESSED`.
- Cost efficiency failures: `token_cost_not_improved`, `wall_cost_not_improved`.
- Wall ratio: `1.211`.
- Token ratio: `1.016`.
- Warning clean gate: `PASS`.
- Wall ledger conserved rate: `1.0` for both arms.

### Training eligibility correction
P96 exposed a training gate leak: cost-regressed but sample-sufficient rows were initially marked `TRAINING_ELIGIBLE`. The gate was tightened:

- If sample is insufficient, posture remains `OBSERVATION_ONLY_SAMPLE_INSUFFICIENT`.
- If sample is sufficient and cost efficiency regresses, posture becomes `OBSERVATION_ONLY_COST_REGRESSED`.
- Recomputed P96 bundle now reports `training_eligibility_posture.status=OBSERVATION_ONLY_COST_REGRESSED`.

### Verification
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "preflight_sentinel or warning_ledger_preserves_source_attribution_metadata or warning_ledger_dirty or rubric_returns_when_receipts_pass_but_provider_tokens_missing or evidence_bundle_reports_rubric_contract_summary"` -> 5 passed.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "training_posture_observation_only_when_cost_efficiency_regresses or separates_delivery_lift_from_cost_efficiency_regression"` -> 2 passed.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_capability_tasks_schema.py tests/nexus/codeintel/test_graph_builder.py -q` -> 240 passed.
- `python3 -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/warning_ledger.py` -> PASS.

### Gate posture
- PASS: docs lane 3-task x1 verified delivery uplift.
- PASS: cost telemetry safety and warning/wall observability.
- RETURN: cost-efficiency improvement claim; wall and token both regressed.
- RETURN: training export; sample is sufficient, but cost efficiency is regressed.

### Next Required Cut
Do not run x3 yet. First isolate why with-nexus wall ratio is `1.211` despite no R/hyper and no hidden retry. The dominant component is model gateway/provider wait, so the next single-variable optimization should target gateway/provider wait or prompt/transport, not governance gates.

## P97 Addendum - Two-Layer Cost Attribution

### Objective
Explain the P96 cost regression before any x3 expansion. Use two layers: structural timing and behavioral payload. Only allow optimization when the dominant component has enough confidence.

### Layer A - Structural cost

- Average wall ratio: `1.211`.
- Average gateway total with Nexus: `66.9961s`.
- Average gateway total without Nexus: `55.9297s`.
- Average gateway provider wait with Nexus: `66.9958s`.
- Average gateway provider wait without Nexus: `55.9295s`.
- Average gateway parse time is negligible: `0.0002s` vs `0.0001s`.
- R/hyper wall: `0`.
- Hidden retry wall: `0`.
- Model calls ratio: `1.0`.

### Layer B - Behavioral cost

- Prompt purity median: `1.0`.
- Prompt purity max: `1.0`.
- Nexus control chars: `0`.
- Governance contract chars: `0`.
- Token ratio: `1.016`.
- Prompt chars delta per matched task: `0`.

### Per-stratum attribution

| Task | Wall delta | Token delta | Provider wait delta | Confidence | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `docs-lane-public-field-contract-001` | `+38.9180s` | `+4937` | `+37.9762s` | `0.9758` | provider-wait regression, optimization allowed |
| `docs-lane-contextual-evidence-contract-001` | `+15.3981s` | `+503` | `+14.5546s` | `0.9452` | provider-wait regression, optimization allowed |
| `docs-lane-config-contract-001` | `-18.5979s` | `-2411` | `-19.3318s` | `1.0` | Nexus faster, no optimization needed |

### Counterfactual check

- If provider wait is unchanged, the two failed-bare/uplift strata still explain the P96 wall regression.
- Prompt trimming is not the first cut: prompt chars are equal between arms and prompt purity is `1.0`.
- Governance gates are not the first cut: no hidden retry, no R/hyper, and receipts/rubric/warning/wall gates are clean.

### Gate posture

- PASS: cost regression is attributable.
- RETURN: cost regression is not yet eliminated.
- HOLD: no x3 expansion until repeatability confirms provider-wait regression is stable across another x1 or a no-op provider probe.

### Next Required Cut
Run a P98 provider-wait repeatability probe with the same frozen 3-task x1 configuration, or a cheaper provider-only timing probe if available. Compare `with_nexus_new` versus `with_nexus_prev` before changing code. Only if the provider-wait delta repeats with confidence >= `0.6` should P99 optimize gateway/provider wait.

## P98 Addendum - Provider-Wait Repeatability Probe

### Objective
Check whether the P96 provider-wait regression is repeatable under the same frozen 3-task x1 setup, with same-batch bare control. Do not optimize yet.

### Result

- P98 report: `.nexus/reports/p98_provider_wait_repeatability_x1/evidence_bundle.json`.
- With Nexus: 3/3 executed, 3/3 semantic verified, trust mismatch 0.
- Without Nexus: 0/3 eligible.
- Bare infra invalid reasons: `quota_exhausted` x2, `timeout_before_model_call` x1.
- `public_delivery_gate=FAIL` due `run_eligibility_incomplete`.
- `public_cost_claim_gate=FAIL` due missing bare token/provider telemetry.
- `public_cost_efficiency_claim_gate=RETURN`.
- `training_eligibility_posture=OBSERVATION_ONLY_TELEMETRY_INVALID`.

### Same-batch control finding

The first bare task also stalled and ended infra-invalid after `179.0625s`, while with-nexus first task took `163.8079s`. This means P98 cannot support a Nexus-specific cost regression claim. The same-batch control points to provider/infra instability for this run.

### Repeatability evidence

With Nexus provider wait remained high:

| Task | P96 with provider wait | P98 with provider wait | Direction |
| --- | ---: | ---: | --- |
| `docs-lane-public-field-contract-001` | `104.7550s` | `162.3360s` | slower, provider wait repeated/increased |
| `docs-lane-contextual-evidence-contract-001` | `59.1083s` | `58.3596s` | stable |
| `docs-lane-config-contract-001` | `37.1242s` | `54.5755s` | slower, but no valid bare pair |

### New accounting blind spot

P98 exposed a no-op accounting issue: `docs-lane-config-contract-001` had `hidden_verifier_passed=True` and a hidden verifier file, but `hidden_verifier_wall_sec` was missing. The wall ledger correctly returned telemetry invalid for that row.

### Gate posture

- PASS: with-nexus correctness and warning cleanliness remained stable.
- RETURN: no cost comparison, because bare arm is infra-invalid.
- RETURN: no x3 expansion.
- NEXT: P99 should be a no-op accounting patch for hidden verifier wall telemetry / wall component coverage before any performance tuning.

## P99-P100 Addendum - Hidden Verifier Wall Telemetry Accounting

### Objective
Fix wall-ledger accounting consistency without changing model behavior, route behavior, prompt payload, or governance gates.

### P99 accounting rule

Hidden verifier wall telemetry is now tri-state:

- `PRESENT`: `hidden_verifier_wall_sec` is measured and can enter the conservation ledger.
- `NOT_APPLICABLE`: this row did not require hidden verifier wall telemetry.
- `MISSING_BUT_REQUIRED`: hidden verifier evidence says the verifier ran or passed, but wall seconds are missing.
- `SUSPICIOUS_ZERO_FILL`: hidden verifier passed but wall seconds were forged or recorded as `0.0`.

The ledger does not guess or backfill missing seconds. Missing required telemetry remains fail-closed.

### P100 same-row recompute

- Diff report: `.nexus/reports/p98_provider_wait_repeatability_x1/p100_accounting_diff.json`.
- Source bundle: `.nexus/reports/p98_provider_wait_repeatability_x1/evidence_bundle.json`.
- Conserved before: `0.6667`.
- Conserved after: `0.6667`.
- Reconciliation error before: `0.0077`.
- Reconciliation error after: `0.0077`.
- Reason before: `wall_ledger_component_missing`.
- Reason after: `hidden_verifier_wall_missing_but_required`, `wall_ledger_component_missing`.
- Cost efficiency remains `RETURN`.
- Training remains `OBSERVATION_ONLY_TELEMETRY_INVALID`.

### Verification

- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "wall_ledger"` -> 6 passed.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_capability_tasks_schema.py tests/nexus/codeintel/test_graph_builder.py -q` -> 242 passed.
- `python3 -m py_compile scripts/bench/capability_ab_runner.py` -> PASS.

### Gate posture

- PASS: accounting failure is now precisely classified.
- PASS: no result was made prettier by recompute; conservation stayed failed.
- RETURN: P98 remains invalid for cost comparison because bare arm was infra-invalid.
- HOLD: no x3 until valid comparison readiness is restored.

### Next Required Cut
P101 should add a valid-comparison-readiness gate: at least 2/3 bare rows must be eligible before cost comparison wording or denominator use. If not, the run must be `INCONCLUSIVE_PROVIDER_VARIANCE` or an infra-stability sample, not a route-cost sample.
