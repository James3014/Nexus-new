# F-02C43 Swarm Architecture Split Inventory

**Status:** `F02C43_SWARM_ARCHITECTURE_SPLIT_INVENTORY`

**Date:** 2026-06-28

## Summary

Inventory of `swarm.py` 13 errors — categorizing by type and identifying safe vs judgment-required fixes.

## Errors by Category

### 1. Encoding / Dict Return Type (6 errors)

| Lines | Error | Safe to Fix? |
|---|---|---|
| 99, 106 | `dict[bytes, bytes] \| dict[str, Any]` not assignable to `Dict[str, Any]` | Yes |
| 99, 106 | No overloads for `__init__` match | Yes |
| 99, 106 | `object` cannot be assigned to `Iterable[list[bytes]]` | Yes |

**Root cause:** `dict(observer(event))` where `observer` returns `dict[bytes, bytes]` or `dict[str, Any]`

**Safe fix:** Change `dict(...)` to `dict(... if isinstance(result, dict) else {})`

### 2. Optional Model / None Guard (2 errors)

| Line | Error | Safe to Fix? |
|---|---|---|
| 200 | `None` cannot be assigned to `str` parameter | Yes |
| 347 | `Unknown \| None` cannot be assigned to `str` | Yes |

**Safe fix:** Add `Optional[str]` type hint or guard with `if model:`

### 3. Client Context Optional Guard (1 error)

| Line | Error | Safe to Fix? |
|---|---|---|
| 231 | `get_client_context` not known attribute of `None` | Yes |

**Safe fix:** Add `if self.client is not None:` guard

### 4. Duplicate Method Redeclaration (1 error)

| Line | Error | Safe to Fix? |
|---|---|---|
| 229 | `_dispatch_remote` obscured by same name | No — needs architecture judgment |

**Root cause:** Two `_dispatch_remote` methods defined in same class

### 5. Remote Dispatch Protocol (3 errors)

| Line | Error | Safe to Fix? |
|---|---|---|
| 270 | Cannot access `_dispatch_remote` for `object` | No — needs architecture judgment |
| 276 | Cannot access `_repair` for `object` | No — needs architecture judgment |
| 335 | Cannot access `history` for `PeerSwarmOrchestrator` | No — needs architecture judgment |

**Root cause:** Dynamic dispatch pattern with `object` type

## Safe to Fix (Agent B)

| Category | Errors | Fix |
|---|---|---|
| Encoding / Dict | 6 | Fix `dict()` conversion |
| Optional Model | 2 | Add `Optional` / guards |
| Client Context | 1 | Add `None` guard |

**Total safe:** 9 errors

## Requires Main Agent Judgment

| Category | Errors | Issue |
|---|---|---|
| Duplicate Method | 1 | Two `_dispatch_remote` methods |
| Remote Dispatch | 3 | Dynamic dispatch with `object` type |

**Total judgment-required:** 4 errors

## Recommended Split

### Batch 1: Safe Fixes (Agent B)
- Fix encoding/dict conversion (6 errors)
- Add optional model guards (2 errors)
- Add client context guard (1 error)

### Batch 2: Architecture (Main Agent)
- Resolve duplicate `_dispatch_remote` (1 error)
- Fix remote dispatch protocol (3 errors)

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Inventory only, no code changed
- Identified 9 safe fixes, 4 judgment-required fixes
