# F-02C35 Swarm Architecture Inventory

**Status:** `F02C35_SWARM_ARCHITECTURE_INVENTORY`

**Date:** 2026-06-26

## Summary

Inventory of `swarm.py` 13 errors — categorizing by type and identifying safe vs judgment-required fixes.

## Errors by Category

### 1. Encoding / Dict Type (4 errors)

| Line | Error | Safe to Fix? |
|---|---|---|
| 99 | `dict[bytes, bytes] \| dict[str, Any]` not assignable | Yes — fix `dict()` call |
| 99 | No overloads for `__init__` match | Yes — fix `dict()` call |
| 106 | Same as above | Yes — fix `dict()` call |
| 106 | Same as above | Yes — fix `dict()` call |

**Root cause:** `dict(result)` where `result` could be `dict[bytes, bytes]` or `dict[str, Any]`

### 2. Optional Model / None (3 errors)

| Line | Error | Safe to Fix? |
|---|---|---|
| 200 | `None` cannot be assigned to `str` parameter | Yes — add `Optional` |
| 347 | `Unknown \| None` cannot be assigned to `str` | Yes — add guard |
| 231 | `get_client_context` not known attribute of `None` | Yes — add guard |

### 3. Duplicate Method / Redeclaration (1 error)

| Line | Error | Safe to Fix? |
|---|---|---|
| 229 | `_dispatch_remote` obscured by same name | No — needs architecture judgment |

**Root cause:** Two `_dispatch_remote` methods defined in same class

### 4. Remote Dispatch Protocol (3 errors)

| Line | Error | Safe to Fix? |
|---|---|---|
| 270 | Cannot access `_dispatch_remote` for `object` | No — needs architecture judgment |
| 276 | Cannot access `_repair` for `object` | No — needs architecture judgment |
| 335 | Cannot access `history` for `PeerSwarmOrchestrator` | No — needs architecture judgment |

**Root cause:** Dynamic dispatch pattern with `object` type

## Safe to Fix (Agent B)

- 4 encoding errors — fix `dict()` conversion
- 3 optional model errors — add `Optional` / guards

**Total safe:** 7 errors

## Requires Main Agent Judgment

- 1 duplicate method error
- 3 remote dispatch protocol errors

**Total judgment-required:** 4 errors

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Inventory only, no code changed
- Identified 7 safe fixes, 4 judgment-required fixes
