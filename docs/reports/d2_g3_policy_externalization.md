# DOCS-D2-G3 Report Retention Policy Externalization

**status: D2_G3_POLICY_EXTERNALIZATION_PASS**

## Start-state

- Start HEAD: `0cb49f4d0e435980fa3198b405e089fdba56c409`
- Commit message: `docs: regenerate report retention inventory`

## Policy inventory

| Policy element | Type | Externalized? | Rationale |
|---|---|---|---|
| `CURRENT_KEEP_FILES` | Static set of filenames | Yes | Pure data, changes with corpus |
| `RAW_HINTS` | Static tuple of tokens | Yes | Pure data, changes with corpus |
| `ACTIVE_WORKSTREAM_PATTERNS` | Static tuple of patterns | Yes | Pure data, changes with workstream |
| `AREA_RETENTION_MAP` | Structural mapping | No | Tied to ReportArea enum, must stay in code |
| Topic classification logic | Decision logic | No | Prefix rules are logic, not data |
| Root retention classification | Decision logic | No | Multi-condition branching, not data |

## Deliverable

- `docs/reports/report_retention_policy_manifest.json` — schema `nexus.report_retention_policy_manifest.v1`

## Files changed

- `scripts/ops/build_report_retention_inventory.py` — added `_load_policy_manifest()`, `PolicyManifest` class, `policy_manifest_path` parameter
- `tests/ops/test_build_report_retention_inventory.py` — added 4 new tests
- `docs/reports/report_retention_policy_manifest.json` — new manifest schema
- `docs/reports/d2_g3_policy_externalization.md` — this file

## Verification

- py_compile: OK
- Existing 11 tests: PASS
- New 4 tests: PASS
- Total tests: 15 passed
- Inventory hash unchanged: YES
- Plan hash unchanged: YES
- Formal outputs not modified: YES
- No reports moved/renamed/deleted: YES

## Non-goals

Policy externalization was implemented.
Schema v2 was not implemented.
Report areas were not modified.
Reports were not reclassified.
Inventory was not regenerated.
Reports were not moved, renamed, archived, or deleted.
D2 is not complete.

## Known residual debt

- Topic classification logic could be externalized in future
- AREA_RETENTION_MAP could be made configurable per area
