# BMF1-OBS — Minimal Receipt-Level Memory Trace

**Status**: `BMF1_OBS_MEMORY_RECEIPT_TRACE_READY`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Added `memory_influence` section to receipt schema. Backward-compatible. No behavior change. Future attribution can now reconstruct memory retrieval traces from receipts.

---

## Files Touched

| File | Change |
|------|--------|
| `nexus/services/local_heal/receipt.py` | Added `memory_influence` section (~10 lines) |

---

## Receipt Schema Extension

```json
"memory_influence": {
  "available": false,
  "trace_status": "TRACE_MISSING",
  "retrieved_count": 0,
  "selected_ids": [],
  "provenance_count": 0,
  "rerank_mode": null,
  "anchor_symbol": null,
  "anchor_file": null,
  "no_memory_match": null,
  "influence_status": "NOT_MEASURED"
}
```

---

## Validation

| Check | Status |
|-------|--------|
| Receipt includes memory_influence | PASS |
| Backward-compatible | PASS |
| Retrieval ranking unchanged | PASS |
| Prompt behavior unchanged | PASS |
| Tests pass (19/19 receipt, 364/364 full) | PASS |

---

## Future Attribution

Can now reconstruct from receipts:
- `retrieved_count` - how many lessons retrieved
- `selected_ids` - which lessons selected
- `provenance_count` - how many had provenance
- `rerank_mode` - whether reranking was used
- `anchor_symbol` / `anchor_file` - what anchor was used
- `no_memory_match` - whether memory was empty

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
