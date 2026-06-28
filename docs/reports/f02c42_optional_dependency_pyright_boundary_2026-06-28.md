# F-02C42 Optional Dependency Pyright Boundary

**Status:** `F02C42_OPTIONAL_DEPENDENCY_PYRIGHT_BOUNDARY`

**Date:** 2026-06-28

## Summary

Attempted to fix optional dependency import errors. These are **impossible to fix** without installing the packages or configuring Pyright to suppress them.

## Errors (Accepted Residual)

| File | Error | Package | Decision |
|---|---|---|---|
| `eternal_memory.py:9` | Missing import `cryptography.fernet` | `cryptography` | Accepted residual |
| `eternal_memory.py:14` | Missing import `arweave` | `arweave` | Accepted residual |
| `web_action_executor.py:6` | Missing import `playwright.async_api` | `playwright` | Accepted residual |
| `web_action_executor.py:9` | Missing import `playwright.async_api` | `playwright` | Accepted residual |

## Investigation

1. **`TYPE_CHECKING` approach**: Does not work — Pyright still reports the import error
2. **`try/except` approach**: Runtime-safe, but Pyright still reports the import error
3. **`# type: ignore`**: Forbidden by task rules

## Root Cause

Pyright's `reportMissingImports` cannot be suppressed without:
- Installing the package (adds to `pyproject.toml`)
- Configuring `pyrightconfig.json` to exclude specific paths
- Using `# type: ignore` (forbidden)

## Recommendation

These 4 errors are **structural residuals** that require a policy decision:

1. **Install optional deps** — Add `cryptography`, `arweave`, `playwright` as optional dependencies in `pyproject.toml`
2. **Configure Pyright** — Add `pyrightconfig.json` with `"reportMissingImports": false` for specific paths
3. **Exclude from scoped gate** — Modify `typecheck.yml` to exclude `eternal_memory.py` and `web_action_executor.py`
4. **Accept as residual** — Document these 4 errors as permanent residuals for T14

## Commands Run

```bash
python3 -m py_compile nexus/core/eternal_memory.py nexus/core/web_action_executor.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 19 | 19 | 0 |

## Scope Statement

- No code changes made
- Documented as structural residual
- Requires policy decision for T14
