# F-02C33 Optional Dependency Residual Decision

**Status:** `F02C33_OPTIONAL_DEPENDENCY_RESIDUAL_DECISION`

**Date:** 2026-06-26

## Summary

Analyzed remaining optional dependency errors. These are accepted residual — cannot be fixed without installing the packages.

## Errors (Accepted Residual)

| File | Error | Package | Decision |
|---|---|---|---|
| `eternal_memory.py:9` | Missing import `cryptography.fernet` | `cryptography` | Accepted residual |
| `eternal_memory.py:14` | Missing import `arweave` | `arweave` | Accepted residual |
| `web_action_executor.py:6` | Missing import `playwright.async_api` | `playwright` | Accepted residual |
| `web_action_executor.py:9` | Missing import `playwright.async_api` | `playwright` | Accepted residual |

## Rationale

1. These are optional dependencies — not required for core functionality
2. Installing them would require adding to `pyproject.toml` which is out of scope
3. Runtime fallback is already implemented (fail-closed / no-op)
4. `TYPE_CHECKING` cannot fully resolve because Pyright still reports the import

## Recommendation

- Mark these 4 errors as accepted residual
- F-02 blocking gate should account for these (require `0 errors` minus documented optional dep residual)
- Future: consider adding `# pyright: reportMissingImports=false` for specific files, or install optional deps in CI

## Commands Run

```bash
python3 -m py_compile nexus/core/eternal_memory.py nexus/core/web_action_executor.py
uv run pyright nexus/core
```

## Scope Statement

- No code changed
- No dependencies installed
- No runtime behavior changed
- Documented as accepted residual
