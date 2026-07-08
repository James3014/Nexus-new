# P1.5 Protocol Classify Format Convergence

## Status

`P1_5_PROTOCOL_CLASSIFY_FORMAT_CONVERGENCE_PASS`

## Summary

`protocol.py.classify_format()` now delegates to `output_understanding._detect_format()` for non-MALFORMED cases, then falls through to existing sub-classification for MALFORMED_OUTPUT. Single canonical source of truth for format detection.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/protocol.py` | Modified — added import + delegated classify_format() to _detect_format() |
| `tests/unit/local_heal/test_protocol.py` | New — 10 tests + parameterized regression |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/protocol.py nexus/services/local_heal/output_understanding.py
pytest tests/unit/local_heal/test_output_understanding.py -v -q
pytest tests/unit/local_heal/test_protocol.py -v -q
```

## Test Counts

- `test_output_understanding.py`: 9/9 passed
- `test_protocol.py`: 19/19 passed (10 individual + 9 parameterized)

## Label Delegation

| Label | Delegated to `_detect_format()`? | Notes |
|-------|----------------------------------|-------|
| `EMPTY` | Yes | via `OutputFormat.EMPTY_OR_REFUSAL` when empty |
| `REFUSAL` | Yes | via `OutputFormat.EMPTY_OR_REFUSAL` when refusal |
| `UNIFIED_DIFF` | Yes | via `OutputFormat.UNIFIED_DIFF` |
| `VALID_SEARCH_REPLACE` | Yes | via `OutputFormat.SEARCH_REPLACE` |
| `FENCED_SEARCH_REPLACE` | Yes | via `OutputFormat.FENCED_SEARCH_REPLACE` |
| `MALFORMED_SEARCH_REPLACE` | No | sub-classification under MALFORMED_OUTPUT |
| `MARKDOWN_FENCED` | No | sub-classification under MALFORMED_OUTPUT |
| `PLAIN_TEXT` | No | sub-classification under MALFORMED_OUTPUT |
| `NATURAL_LANGUAGE` | No | sub-classification under MALFORMED_OUTPUT |

## Explicit Statements

- `protocol.py.classify_format()` now delegates to `output_understanding._detect_format()` for non-MALFORMED cases
- No changes to `parse()`, `validate()`, or other protocol.py methods
- No executor behavior change
- Not P1 complete
- `public_claim_allowed=false`
- `production_ready=false`
