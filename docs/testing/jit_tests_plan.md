# JIT Tests v0 Plan

## Goal

Introduce a low-conflict affected-test lane that lets agents select relevant
pytest targets from changed paths before running broad validation.

## Current Scope

- Add `scripts/ops/select_tests.py` as a pure selector.
- Read `docs/testing/test_impact_map.md` as the source of truth.
- Let `scripts/ops/test_changed.sh` call the selector.
- Add focused unit coverage in `tests/ops/test_select_tests.py`.
- Do not write `.nexus/reports/*`.
- Do not change `scripts/ops/ci_gate.py` in v0.
- Do not run benchmark or broad pytest lanes as part of selector execution.

## Verification

```bash
bash -n scripts/ops/test_changed.sh
uv run python -m py_compile scripts/ops/select_tests.py
uv run pytest -q tests/ops/test_select_tests.py
```

Optional L2 entry smoke:

```bash
bash scripts/ops/test_changed.sh scripts/ops/select_tests.py
```

## Next Wiring Order

1. Keep v0 scoped to `test_changed.sh`.
2. Expand impact-map coverage from observed misses.
3. Add an import graph index at `.nexus/test_impact_index.json`.
4. Add pytest duration and flaky-history metadata.
5. Wire a changed-only lane into `ci_gate.py` after the selector proves stable.
