# P4-I3 Candidate Provider Adapter to CanonicalPatchCandidate Report

## Status: ✅ COMPLETE (committed: `11a48824d`)

## Files Changed (4)

| File | Action |
|------|--------|
| `nexus/services/local_heal/committee_candidate_adapter.py` | +125 — adapter logic |
| `nexus/services/local_heal/committee_routed_tool.py` | +19 — `adapt_candidates()` entry point |
| `nexus/services/local_heal/receipt.py` | +4 — 3 new receipt fields |
| `tests/unit/local_heal/test_p4_committee_candidate_adapter.py` | +165 — 12 tests |

## Conversion Flow

```
raw candidate dict
  → extract candidate_patch + format
  → CanonicalPatchCandidate(raw_output_hash, normalized_patch_hash, source_format, ...)
  → enriched with target_file, target_symbol, line_span, old_block_hash, model_name
  → safety_flags on mismatch
```

## Rejection Conditions

- empty/refusal candidate → rejected
- malformed (no parseable format) → rejected
- target_file mismatch → safety_flags (not rejected at adapter stage)

## Receipt Fields Added

`p4_raw_candidate_count`, `p4_rejected_candidate_count`, `p4_rejected_candidate_reasons`

## Test Results

```
P4-I3:     12 passed
P4-I1+I2:  22 passed
P3 regress: 41 passed
Full suite: 1390 passed, 1 skipped, 0 failed
```

## Next

✅ P4-I3 complete → ready for **P4-I4: Committee Execution Inside P3 Hard-case Path**
