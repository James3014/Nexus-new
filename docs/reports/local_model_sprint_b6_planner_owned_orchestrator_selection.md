# Local Model Sprint B6: Planner-owned Orchestrator Selection

**Status:** LOCAL_MODEL_SPRINT_B6_PLANNER_OWNED_ORCHESTRATOR_SELECTION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/pipeline.py` | Orchestrator selection from `route_context.signal_snapshot` |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Added 4 B6 tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py -q
# 31 passed
```

## What Changed

| Before B6 | After B6 |
|-----------|----------|
| `NEXUS_USE_COMMITTEE` env drives orchestrator selection | `route_context.signal_snapshot.local_committee_enabled` drives selection |
| Env always wins | Signal_snapshot wins when present |
| Legacy env path preserved for non-planner paths | Env fallback only when `signal_snapshot` is empty |

## Selection Logic

```python
signal_snap = route_ctx.get("signal_snapshot", {})
committee_enabled = signal_snap.get("local_committee_enabled", False)
env_committee = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1" if not signal_snap else False
use_committee = committee_enabled or env_committee
```

- If `signal_snapshot` is present: use `local_committee_enabled` from it
- If `signal_snapshot` is empty (legacy path): fallback to `NEXUS_USE_COMMITTEE` env
- Env never overrides signal_snapshot when signal_snapshot is present

## Explicit Statements

- No new route/topology.
- No committee algorithm change.
- Planner-owned path does not use env as authority.
- Legacy env behavior preserved for non-planner paths.
