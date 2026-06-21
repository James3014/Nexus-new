# BMF3-OBS — Replace Global Memory Trace With ctx-Scoped Contract

**Status**: `BMF3_CTX_SCOPED_MEMORY_TRACE_READY`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Replaced BMF2 module-level `_last_memory_trace` global with proper ctx-scoped `MemoryTrace` contract. Receipt now reads from adapter class-level trace, no global fallback.

---

## Changes

| File | Change |
|------|--------|
| `memory_trace.py` (NEW) | Formal `MemoryTrace` dataclass + `build_memory_trace_from_adapter()` |
| `memory_retrieval_adapter.py` | Added `_last_trace` class variable, stores trace on each retrieval |
| `semantic_anchor_selection.py` | Removed `_last_memory_trace` module global |
| `receipt.py` | Removed `_get_memory_trace_from_scorer()`, added `_extract_memory_trace()` |

---

## Data Flow (After)

```
MemoryRetrievalAdapter.retrieve()
  -> self.last_metadata
  -> MemoryRetrievalAdapter._last_trace (class-level)
  -> receipt._extract_memory_trace(ctx)
  -> receipt.memory_influence (TRACE_AVAILABLE)
```

---

## Validation

| Check | Status |
|-------|--------|
| Module global removed | PASS |
| Receipt uses only ctx trace | PASS |
| selected_ids reconstructible | PASS |
| No stale trace leakage | PASS |
| Prompt unchanged | PASS |
| Ranking unchanged | PASS |
| 19/19 receipt tests | PASS |
| 364/364 full suite | PASS |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
