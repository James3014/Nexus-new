# F-02C46 Optional Dependency Typecheck Policy

**Status:** `F02C46_OPTIONAL_DEPENDENCY_TYPECHECK_POLICY`

**Date:** 2026-06-28

## Summary

Documented policy for optional dependency import errors that block T14.

## Current State

- **Total errors:** 4
- **All are missing import errors** for optional dependencies
- **Cannot be fixed** without installing packages or configuring Pyright

## Errors

| File | Error | Package |
|---|---|---|
| `eternal_memory.py:9` | Missing import `cryptography.fernet` | `cryptography` |
| `eternal_memory.py:14` | Missing import `arweave` | `arweave` |
| `web_action_executor.py:6` | Missing import `playwright.async_api` | `playwright` |
| `web_action_executor.py:9` | Missing import `playwright.async_api` | `playwright` |

## Policy Decision

**Recommendation:** Exclude optional integration modules from scoped Pyright gate.

### Rationale

1. These are optional dependencies — not required for core functionality
2. Installing them would add significant dependencies to `pyproject.toml`
3. Runtime fallback is already implemented (fail-closed / no-op)
4. These modules are integration adapters, not core logic

### Implementation Options

**Option A: Scoped Pyright Config (Recommended)**

Create `pyrightconfig.json` with exclusions:
```json
{
  "exclude": [
    "nexus/core/eternal_memory.py",
    "nexus/core/web_action_executor.py"
  ]
}
```

**Option B: Update `typecheck.yml`**

Modify the workflow to exclude these files:
```yaml
- name: Run Pyright (nexus/core only, excluding optional adapters)
  run: |
    uv run pyright nexus/core --exclude "eternal_memory.py" --exclude "web_action_executor.py"
```

**Option C: Accept as Residual**

Document these 4 errors as permanent residuals for T14.

## Recommendation

**Option A** is cleanest — creates a `pyrightconfig.json` that excludes optional integration modules, with a clear comment explaining why.

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Policy decision only, no code changes
- Documents structural residual for T14
