# F-05E Root JSONL Residual Audit

**Status:** `F05E_ROOT_JSONL_RESIDUAL_AUDIT`

**Date:** 2026-06-29

## Summary

Audited 6 remaining root JSONL files. Moved 1 safe file, skipped 5 with references.

## Audit Results

| File | Classification | Action |
|---|---|---|
| `events_sourced.jsonl` | Script reference (`generate_nexus_measurements.py`) | Skipped |
| `results_deepswe_final_v26.jsonl` | Doc reference (`NEXUS_FORENSIC_EVIDENCE_PACK.md`) | Skipped |
| `results_deepswe_full.jsonl` | Script reference (5 scripts in `scripts/ops/`) | Skipped |
| `run_1_belief_extract.jsonl` | Doc reference (`acceptance_summary.md`) | Skipped |
| `tracelog_governance_hardening.jsonl` | Compliance reference | Skipped |
| `tracelog_nexus_core_outcome_schema.py.jsonl` | Inventory only | Moved |

## Moved

| File | Destination |
|---|---|
| `tracelog_nexus_core_outcome_schema.py.jsonl` | `docs/reports/root-generated/2026-06-25/` |

## Before/After

| Metric | Before | After |
|---|---|---|
| Root JSONL count | 6 | 5 |

## Commands Run

```bash
find . -maxdepth 1 -type f -name '*.jsonl' -print | sort
rg -n --fixed-strings "<filename>" .
```

## Scope Statement

- Only 1 file moved (proven safe by reference check)
- 5 files skipped due to script/doc/compliance references
- F-05 still not complete
