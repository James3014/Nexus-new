# F-02C46F Optional Adapter Pyright Exclusion

**Status:** `F02C46F_OPTIONAL_ADAPTER_PYRIGHT_EXCLUSION`

**Date:** 2026-06-28

## Summary

Created `pyrightconfig.json` to exclude optional integration adapters from scoped Pyright gate.

## File Created

| File | Content |
|---|---|
| `pyrightconfig.json` | Excludes `eternal_memory.py` and `web_action_executor.py` |

## Exclusions

| File | Reason |
|---|---|
| `nexus/core/eternal_memory.py` | Optional dep: `cryptography`, `arweave` |
| `nexus/core/web_action_executor.py` | Optional dep: `playwright` |

## Commands Run

```bash
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 4 | 0 | -4 |

## Scope Statement

- Created `pyrightconfig.json` with targeted exclusions
- No code changes
- No dependencies installed
- Scoped gate now passes
