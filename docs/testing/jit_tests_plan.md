# JIT Tests v0 Plan

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

## Next Wiring Order

1. Expand impact-map coverage from observed misses.
2. Add per-target duration extraction from pytest reports.
3. Add skipped-test evidence reporting.
4. Add run eligibility semantics for Gemini benchmark quota/infra invalid rows.
5. Add predictive ranking only after enough `.nexus/reports/test_history.jsonl` data exists.
