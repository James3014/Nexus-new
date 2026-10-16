# DOCS-D2-G3C Report Retention Policy Authority Closure

**status: D2_G3C_POLICY_AUTHORITY_PASS**

## Start-state

- Start HEAD: `080baafbd6de5c9cba44e0b4200b133ae7b3b20a`
- End pre-commit HEAD: `080baafbd6de5c9cba44e0b4200b133ae7b3b20a`

## Retrieved lesson

- Source: `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- Applicable lesson: Manifest-driven execution must fail closed when the manifest is missing or incomplete, rather than silently falling back to hardcoded defaults.

## Authority decision

**Repository default execution**: Policy manifest is authoritative. If missing, invalid, or incomplete, fail closed.

**Isolated tests/external callers**: Fallback allowed only via explicit `allow_default_policy_fallback=True` parameter.

**Reason**: Silent fallback in production can mask configuration drift. Explicit opt-in ensures test isolation while maintaining production safety.

## Repository default behavior

When using default `docs/reports` directory:
- Policy manifest `docs/reports/report_retention_policy_manifest.json` must exist
- Must have valid schema `nexus.report_retention_policy_manifest.v1`
- Must have version `v1`
- Must have all required fields with correct types
- Missing/invalid manifest → `FileNotFoundError` with clear message

## Isolated fallback behavior

When `allow_default_policy_fallback=True`:
- Missing manifest → uses hardcoded defaults (ACTIVE_WORKSTREAM_PATTERNS, CURRENT_KEEP_FILES, RAW_HINTS)
- Missing explicit manifest path → uses hardcoded defaults
- Used by tests and external callers that don't have the manifest

## Manifest validation rules

- `schema` must equal `nexus.report_retention_policy_manifest.v1`
- `version` must equal `v1`
- `active_workstream_patterns` must be a list of strings
- `current_keep_files` must be a list of strings
- `raw_hints` must be a list of strings
- `root_retention_keywords` must be an object
- `root_retention_keywords.human_entrypoint` must be a list of strings

Error messages specify the exact invalid field.

## Tests added

| Test | Purpose |
|---|---|
| `test_default_repository_execution_requires_policy_manifest` | Fails closed when manifest missing in repo-default path |
| `test_policy_manifest_rejects_missing_required_field` | Fails on missing required fields |
| `test_policy_manifest_rejects_wrong_field_type` | Fails on wrong field types |
| `test_explicit_isolated_fallback_preserves_legacy_behavior` | Fallback works with explicit flag |
| `test_custom_active_pattern_changes_excluded_paths` | Manifest patterns affect exclusion |
| `test_custom_raw_hint_changes_archive_classification` | Manifest hints affect classification |
| `test_custom_human_keyword_changes_entrypoint_classification` | Manifest keywords affect entrypoint |
| `test_policy_manifest_missing_file_fails_closed` | Explicit path with missing file fails |
| `test_policy_manifest_missing_fields_rejects` | Missing fields raise ValueError |

## Verification

- py_compile: OK
- Manifest JSON: valid
- Focused tests: 21 passed
- Test count: 21
- Direct CLI: status=PASS, dry_run=True, rows=2063
- Module CLI: status=PASS, dry_run=True, rows=2063
- Missing-manifest negative test: exit=1, clear error
- Inventory hash unchanged: YES
- Plan hash unchanged: YES
- git diff --check: clean
- Deletion audit: no deleted files

## Non-goals

The policy manifest is authoritative for repository-default execution.
Silent fallback is not allowed for repository-default execution.
Fallback remains available only through an explicit isolated/test path.
Inventory schema was not changed.
Formal inventory outputs were not regenerated.
No reports were moved, renamed, archived, or deleted.
