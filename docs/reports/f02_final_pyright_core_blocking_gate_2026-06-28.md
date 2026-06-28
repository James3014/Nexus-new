# F-02 Final Pyright Blocking Gate Promotion

**Status:** `F02_PYRIGHT_CORE_BLOCKING_GATE_PROMOTED`

**Date:** 2026-06-28

## Summary

Promoted scoped Pyright from observation-only to blocking CI gate.

## File Changed

| File | Change |
|---|---|
| `.github/workflows/typecheck.yml` | Removed `continue-on-error`, updated name and summary |

## Changes Applied

1. **Workflow name** from "observation" to "nexus/core blocking"
2. **Job name** from "Pyright Observation" to "Pyright Scan (nexus/core blocking)"
3. **Removed job-level `continue-on-error: true`**
4. **Removed step-level `continue-on-error: true`**
5. **Updated summary** to indicate blocking behavior
6. **Added note** about `pyrightconfig.json` exclusions

## Exclusions (from `pyrightconfig.json`)

| File | Reason |
|---|---|
| `nexus/core/eternal_memory.py` | Optional dep: `cryptography`, `arweave` |
| `nexus/core/web_action_executor.py` | Optional dep: `playwright` |

## Commands Run

```bash
uv run pyright nexus/core
git diff --check
```

## Results

| Metric | Before | After |
|---|---|---|
| Pyright errors | 0 | 0 |
| Workflow type | observation | blocking |
| `continue-on-error` | true | removed |

## Scope Statement

- Scoped to `nexus/core` only
- Optional adapters excluded via `pyrightconfig.json`
- Not full repo type safety
- F-02 scoped completion declared
