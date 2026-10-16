# Local Model Sprint B7.3: Reproduction Contract Bridge

**Status:** LOCAL_MODEL_SPRINT_B7_3_REPRODUCTION_CONTRACT_BRIDGE_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Bridge sets `skip_reproduction=True` when no repro_script |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Updated test for provider call count |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 64 passed
```

## What Changed

| Before B7.3 | After B7.3 |
|-------------|------------|
| Bridge builds HealContext without `skip_reproduction` | Bridge sets `skip_reproduction=True` when no `repro_script` in route_context |
| `NO_REPRO_SCRIPT` error | Pipeline skips reproduction, uses `problem_statement[:3000]` as repro_evidence |
| Pipeline blocked at reproduction phase | Pipeline passes reproduction and reaches planning |

## Reproduction Contract Logic

```python
route_ctx = ctx.route_context
repro_script = route_ctx.get("repro_script", "")
skip_repro = not bool(repro_script)

heal_ctx = LegacyHealContext(
    ...
    skip_reproduction=skip_repro,
    repro_script=repro_script,
)
```

- If `repro_script` in route_context → use it
- If no `repro_script` → `skip_reproduction=True`, pipeline uses `problem_statement[:3000]`
- verify_script is NOT silently treated as repro_script

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- Pipeline must not fail with NO_REPRO_SCRIPT when skip_reproduction=True.
