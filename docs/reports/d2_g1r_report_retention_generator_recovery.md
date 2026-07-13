# DOCS-D2-G1R Report Retention Generator Recovery

**status: D2_G1R_GENERATOR_RECOVERY_PASS**

## Start-state

- Start HEAD: `86104ef6b7eb95421506ad79f45e78f84997b854`
- Generator lines before: 23 (truncated)
- Staged files before: none

## Lessons retrieved

- Source: `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- Applicable lesson: CLI adapters that combine optional `Path` args with output-dir helpers must treat both empty string and `.` as unset. Regression coverage for default CLI output paths required.
- Plan impact: Preserved `output_dir` guard in `main()` and `resolve_report_output` usage.

## Root cause

Generator file was truncated to 23 lines during a prior workstream, losing all core logic including recursive discovery, area classification, manifest support, and the `ReportArea` enum.

## Files changed

- `scripts/ops/build_report_retention_inventory.py` — restored from HEAD baseline + added `ReportArea` enum, manifest-driven area mapping, recursive `rglob` discovery, area-specific retention behavior (362 lines)
- `tests/ops/test_build_report_retention_inventory.py` — unchanged (196 lines)
- `docs/reports/report_area_manifest.json` — unchanged (12 lines)
- `docs/reports/d2_g1r_report_retention_generator_recovery.md` — new (this file)

## Implementation details

- Generator lines after: 362
- Recursive scan: `reports_dir.rglob("*")` with `path.is_file()` filter
- Manifest mapping: loaded from `DEFAULT_AREA_MANIFEST` (`docs/reports/report_area_manifest.json`), schema `nexus.report_area_manifest.v1`
- Unknown-area behavior: `report_area = "unknown"`, `retention_class = "unknown_hold"`, `reason = "unknown_nested_report_area"`
- Direct CLI bootstrap: `REPO_ROOT = Path(__file__).resolve().parents[2]` with `sys.path.insert`

## Verification

- py_compile: OK
- Manifest JSON: valid
- Focused tests: 11 passed
- Test count: 11
- Direct CLI dry-run: OK (2048 rows scanned, status PASS)
- JSON hash unchanged: YES
- Markdown hash unchanged: YES
- git diff --check: clean
- Deletion audit: no deleted files

## Real-corpus dry-run summary

- Rows scanned: 2048
- Excluded active workstreams: 49
- Report area counts: archive=670, root=1320, experiment=20, generated=19, asset=11, handoff=8
- Status: PASS

## Non-goals (explicit)

This phase restored the generator baseline only.
Formal inventory outputs were not regenerated.
Policy externalization was not implemented.
Duplicate detection was not implemented.
Reports were not moved, renamed, archived, or deleted.
D2 is not complete.

## Known residual debt

- Policy externalization not implemented
- Duplicate detection not implemented
- Formal inventory regeneration not performed
- Inventory schema not upgraded to v2

## Governance boundary

- Reports corpus not治理完成
- Not production ready
- No public claim allowed
