# JIT Tests Plan

## Goal

Introduce a low-conflict affected-test lane that lets agents select relevant
pytest targets from changed paths before running broad validation.

## Current Scope

- Add `scripts/ops/select_tests.py` as a pure selector.
- Read `docs/testing/test_impact_map.md` as the source of truth.
- Read `.nexus/test_impact_index.json` when present for import-derived test hits.
- Add `scripts/ops/build_test_impact_index.py` to generate the import index.
- Let `scripts/ops/test_changed.sh` call the selector.
- Add focused unit coverage in `tests/ops/test_select_tests.py`.
- Do not write `.nexus/reports/*`.
- Do not run benchmark or broad pytest lanes as part of selector execution.

## Verification

```bash
bash -n scripts/ops/test_changed.sh
uv run python -m py_compile scripts/ops/select_tests.py
uv run python -m py_compile scripts/ops/build_test_impact_index.py
uv run pytest -q tests/ops/test_select_tests.py
uv run pytest -q tests/ops/test_build_test_impact_index.py
```

Optional L2 entry smoke:

```bash
bash scripts/ops/test_changed.sh scripts/ops/select_tests.py
```

## v1 Behavior

Selection order:

1. Import index direct hits from `.nexus/test_impact_index.json`.
2. Documentation-backed path mapping from `docs/testing/test_impact_map.md`.
3. Fallback core smoke targets for unmapped paths.

JSON output includes:

- `targets`
- `reasons`
- `confidence`
- `risk`
- `sources`
- `history`

## v2 Behavior

Selection now also reads `.nexus/reports/test_history.jsonl` when present.

- Flaky targets are prioritized earlier.
- Faster historical targets are prioritized before slower targets when other risk signals are equal.
- High-risk escalation is read from the `風險` column in `docs/testing/test_impact_map.md`; high-risk rows receive the policy-gate safety target and expose `risk_reasons` from the `風險原因` column.
- `ci_gate.py --changed-only` writes changed-only run evidence back to test history.

## v3 Behavior

Changed-only CI now records richer evidence without changing the selector-only
contract.

- `ci_gate.py --changed-only` emits a JUnit XML report and aggregates `target_durations` into `.nexus/reports/test_history.jsonl`.
- Selector JSON includes `selected_count`, `fallback_used`, `high_risk_escalated`, `risk_reasons`, `unmatched_paths`, and `retry_recommended`.
- Historical flaky targets are surfaced through `retry_recommended`; v3 recommends retry but does not automatically rerun.
- Fallback and high-risk selection are explicit evidence fields, so skipped/unmatched coverage can be reviewed before benchmark interpretation.

## v4 Observation Mode

Nexus now records Launchable-style observations without enabling ML ranking.

- `ci_gate.py --changed-only` writes latest selection evidence to `.nexus/reports/changed_only_selection.json`.
- The same changed-only evidence is appended to `.nexus/reports/jit_observation.jsonl`.
- `scripts/ops/jit_coverage_gap.py` summarizes fallback-heavy paths, unmatched paths, high-risk paths, and slow generic targets into `.nexus/reports/jit_coverage_gap.json`.
- ML ranking stays disabled until observation history is large enough and miss-rate can be checked against defensive full runs.

Verification:

```bash
uv run pytest -q tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets
uv run pytest -q tests/ops/test_jit_coverage_gap.py
uv run python scripts/ops/jit_coverage_gap.py
```

## v4/v5 Completion Matrix

This matrix is the stored implementation boundary as of 2026-04-28.

| Item | Status | Evidence | Next action |
| :--- | :--- | :--- | :--- |
| Benchmark eligibility schema | done | `scripts/bench/capability_ab_runner.py` annotates `provider`, `model_name`, `run_eligible`, `infra_invalid_reason`, `invocation_started`, `model_response_received`, and `nexus_bootstrap_completed`; benchmark summaries expose `eligible_n` and `infra_invalid_n`. | Keep in all Gemini vs Nexus reports. |
| Changed-only flaky auto retry v0 | planned | v3 already emits `retry_recommended`; no `retry_attempts`, `retry_targets`, or `retry_success` gate behavior yet. | Implement only after more history confirms flaky labels are reliable. |
| JIT evidence report file | done | `ci_gate.py --changed-only` writes `.nexus/reports/changed_only_selection.json` and appends `.nexus/reports/jit_observation.jsonl`. | Keep latest report path visible in CI logs. |
| Path-target correlation index | done, opt-in | `scripts/ops/jit_feedback.py` builds `.nexus/test_impact_stats.json` from changed-only observations and nightly missed-candidate evidence. | Keep collecting data; do not switch selector defaults yet. |
| Coverage gap report | done | `scripts/ops/jit_coverage_gap.py` writes `.nexus/reports/jit_coverage_gap.json`. | Use report to curate impact-map rows, not auto-edit them. |
| Predictive ranking v0 | done, opt-in | `select_tests.py` supports `--ranking static|predictive`; JSON includes `target_scores` with score reasons, default remains `static`. | Use predictive only for analysis until miss-rate evidence is stable. |
| Nightly feedback loop | done, offline | `scripts/ops/jit_feedback.py` back-propagates full-run failures not selected by changed-only into `.nexus/reports/jit_missed_candidates.json`. | Wire into nightly after report schema is observed in real runs. |

## v4 Stored Backlog

### Benchmark Eligibility Schema

Purpose: keep quota, auth, CLI, pre-model timeout, and parse failures out of
model ability denominators.

Required row fields:

- `run_eligible: bool`
- `infra_invalid_reason: quota_exhausted | auth_failed | cli_missing | timeout_before_model_call | parse_error | null`
- `model_name`
- `provider`
- `invocation_started: bool`
- `model_response_received: bool`
- `nexus_bootstrap_completed: bool`

Acceptance:

- Quota/auth/CLI failures do not enter solve-rate denominators.
- Reports include `eligible_n`, `infra_invalid_n`, and solve rate.
- Gemini baseline and Gemini+Nexus share the same eligibility rule.

### Changed-Only Flaky Auto Retry v0

Purpose: turn v3 `retry_recommended` into a conservative changed-only retry.

Rules:

- Only enabled in `ci_gate.py --changed-only`.
- Retry each flaky target at most once.
- Gate passes when first run fails but retry passes.
- Deterministic failure still fails the gate.
- Non-flaky targets are not automatically retried.

Evidence fields:

- `retry_attempts`
- `retry_targets`
- `retry_success`

### JIT Evidence Report File

Purpose: keep latest JIT evidence readable without digging through JSONL.

Output:

- `.nexus/reports/changed_only_selection.json`

Required content:

- changed paths
- selected targets
- unmatched paths
- fallback used
- high-risk escalated
- retry recommended / retried
- target durations
- confidence / risk / sources

## Future ML Plan

Do not add ML until observation data proves it is useful.

1. Collect at least 2-4 weeks of changed-only and full-regression observations.
2. Offline nightly feedback can mark full-run failures not selected by changed-only as `missed_candidate`.
3. The selector can expose an explainable score before ML:
   - import index hit: +5
   - impact map hit: +3
   - high-risk impact-map metadata: +2
   - historical failure rate: +2
   - flaky target: +1
   - missed-candidate recovery: +3
   - duration penalty for slow generic targets
4. `--ranking static|predictive` exists; keep `static` as default.
5. Only switch default after miss rate and saved runtime are both acceptable.

## v5 Stored Backlog

### Path-Target Correlation Index

Purpose: learn which changed paths historically correlate with failing test
targets without jumping straight to ML.

New file:

- `.nexus/test_impact_stats.json`

Inputs:

- changed-only history
- nightly history
- failed target durations

Scoring inputs:

- direct import index hit: high weight
- impact map hit: medium weight
- historical co-failure: additive weight
- high-risk impact-map metadata: safety weight

Acceptance:

- Selector JSON shows score breakdown for each target.
- Sorting stays explainable.
- Predictive ranking is opt-in and does not change default CI behavior.

### Coverage Gap Report

Purpose: find impact-map gaps before they become missed tests.

Output:

- `.nexus/reports/jit_coverage_gap.json`

Detect:

- fallback-heavy paths
- high-risk but generic mapping
- slow generic targets
- unmatched docs/scripts paths

Acceptance:

- Report lists top mapping gaps.
- Report may suggest impact-map rows but does not edit files automatically.

### Predictive Ranking v0

Purpose: add simple explainable scoring before ML.

Example formula:

```text
score = import_hit*5 + impact_map_hit*3 + failure_rate*2 + flaky*1.5 + high_risk*2 - avg_duration_penalty
```

Acceptance:

- Selector JSON includes `target_scores` with `score` and `score_reasons`.
- CLI supports `--ranking static|predictive`.
- Default remains `static` until history proves predictive ranking is safe.

### Nightly Feedback Loop

Purpose: calibrate JIT with full regression misses.

Rules:

- When nightly full regression fails, compare failing targets with recent changed-only selections.
- If changed-only did not select the failing target, record `missed_candidate`.
- Coverage gap report can cite missed candidates.

## Next Wiring Order

1. Wire `scripts/ops/jit_feedback.py` into nightly reporting after two or more real history samples confirm the schema.
2. Expand impact-map coverage from observed fallback/unmatched paths and missed candidates.
3. Add optional flaky auto-retry after retry recommendation data is stable.
4. Evaluate predictive ranking with saved-runtime and miss-rate reports before considering a default change.

Lesson:

- Predictive selection must be an analysis lane before it becomes a gate lane. The safe default is still deterministic static selection; `.nexus/test_impact_stats.json` is evidence for review and tuning, not an automatic product claim.
