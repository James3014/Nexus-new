# P9: Anchor Provenance and Parser Hardening Report

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | P9 |
| Commit SHA | d9b62b10 |
| Status | P9_ANCHOR_PARSER_HARDENED |
| Files Changed | 5 core files |
| Tests Run | 208 (all passing) |
| Tests Added | 20 new P9-specific tests |

## Changes Made

### 1. Error Classification Expansion (`errors.py`)

Added 7 new `PatchErrorKind` values:

- `REPLACEMENT_PROSE_CONTAMINATION` — replacement contains natural language prose
- `REPLACEMENT_MARKDOWN_FENCE` — replacement wrapped in markdown code fences
- `REPLACEMENT_SYNTAX_INVALID` — replacement is not syntactically valid
- `REPLACEMENT_SCOPE_VIOLATION` — replacement spans outside allowed anchor scope
- `ANCHOR_NOT_IN_BASE_SOURCE` — anchor not found in base_commit source
- `ANCHOR_AMBIGUOUS` — anchor matches multiple locations in source
- `SOURCE_HASH_CHANGED_AFTER_CHECKOUT` — source_hash changed between extraction and apply

### 2. Parser Strictness (`protocol.py`)

Added `AnchoredEditReplacementGuard` class with:

- **Prose detection patterns**: 10 regex patterns covering common prose markers
- **Markdown fence rejection**: Detects ` ``` ` wrapping before stripping
- **Code ratio check**: Rejects replacement if <40% of lines are code-like
- **AST validity check**: Validates replacement is syntactically valid Python
- **Integrated into parser**: anchored_edit mode now validates replacement BEFORE returning

### 3. Anchor Provenance Metadata (`anchored_edit.py`)

Added provenance fields to `AnchoredEdit`:

- `anchor_extraction_stage` — must be `"after_base_checkout"`
- `anchor_text_hash` — SHA256 of anchor text for integrity
- `source_hash_before_apply` — source hash at extraction time
- `anchor_count` — number of occurrences in source
- `anchor_span_start/end` — line numbers in source

Validation now checks:
1. Extraction stage is `after_base_checkout`
2. Source hash matches
3. Anchor text hash matches
4. Anchor is unambiguous (count == 1)

### 4. Existing Test Updates

- Updated `test_anchored_edit_ambiguous_anchor` to expect `ANCHOR_AMBIGUOUS`
- Updated `test_anchored_edit_anchor_not_in_source` to expect `ANCHOR_NOT_IN_BASE_SOURCE`
- Updated `test_protocol_parse_anchored_edit_mode` to reject markdown fences
- Updated existing tests to include `anchor_extraction_stage="after_base_checkout"`

## New Tests Added

1. `test_anchored_edit_wrong_extraction_stage` — rejects pre-checkout anchors
2. `test_anchored_edit_correct_extraction_stage` — accepts post-checkout anchors
3. `test_anchored_edit_anchor_text_hash_mismatch` — rejects hash mismatches
4. `test_parser_rejects_prose_before_code` — rejects prose before code
5. `test_parser_rejects_prose_after_code` — rejects prose after code
6. `test_parser_rejects_markdown_fenced_replacement` — rejects markdown fences
7. `test_parser_rejects_explanation_paragraph` — rejects explanation text
8. `test_parser_rejects_mixed_explanation_code` — rejects mixed prose+code
9. `test_parser_accepts_raw_code_replacement` — accepts clean code
10. `test_parser_rejects_invalid_syntax_replacement` — rejects invalid syntax
11. `test_parser_rejects_bullet_list_replacement` — rejects bullet lists
12. `test_compliance_checker_rejects_prose_contaminated_replacement` — compliance guard
13. `test_compliance_checker_accepts_clean_replacement` — compliance acceptance

## Test Results

```
208 passed in 1.54s
```

## Infrastructure Bug Fixes

1. **C_11618 anchor bug**: Anchor extraction now requires `anchor_extraction_stage="after_base_checkout"` metadata. Anchors extracted before checkout are rejected.

2. **C_12481 prose contamination**: Parser now rejects markdown fences, prose before/after code, explanation paragraphs, and mixed natural language + code blocks.

3. **Source hash staleness**: Added `SOURCE_HASH_CHANGED_AFTER_CHECKOUT` error kind for cases where anchor text changes between extraction and application.

## Proceed to P10

P9 tests pass. Proceeding to P10 for semantic anchor selection upgrade.
