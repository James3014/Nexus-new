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
- `nexus/core`, `nexus/security`, and `scripts/ops/ci_gate.py` changes are marked high risk and receive the policy-gate safety target.
- `ci_gate.py --changed-only` writes changed-only run evidence back to test history.

## v3 Behavior

Changed-only CI now records richer evidence without changing the selector-only
contract.

- `ci_gate.py --changed-only` emits a JUnit XML report and aggregates `target_durations` into `.nexus/reports/test_history.jsonl`.
- Selector JSON includes `selected_count`, `fallback_used`, `high_risk_escalated`, `unmatched_paths`, and `retry_recommended`.
- Historical flaky targets are surfaced through `retry_recommended`; v3 recommends retry but does not automatically rerun.
- Fallback and high-risk selection are explicit evidence fields, so skipped/unmatched coverage can be reviewed before benchmark interpretation.

## Next Wiring Order

1. Expand impact-map coverage from observed misses.
2. Add run eligibility semantics for Gemini benchmark quota/infra invalid rows.
3. Add optional flaky auto-retry after retry recommendation data is stable.
4. Add predictive ranking only after enough `.nexus/reports/test_history.jsonl` data exists.
