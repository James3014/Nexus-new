# P1-1 Canonical Candidate Contract

## Status

`P1_1_CANONICAL_CANDIDATE_CONTRACT_PASS`

## Summary

Introduced the canonical model-output contract (`CanonicalPatchCandidate` and `OutputUnderstandingResult`) and a focused output-understanding layer for core local-heal formats. No executor integration, no apply/hash truth work, no route changes.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/output_understanding.py` | New — contract objects + `understand_output()` |
| `tests/unit/local_heal/test_output_understanding.py` | New — 9 tests |
| `docs/reports/p1_1_canonical_candidate_contract_v0.md` | New — this report |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/output_understanding.py nexus/services/local_heal/protocol.py tests/unit/local_heal/test_output_understanding.py
pytest tests/unit/local_heal/test_output_understanding.py -q
pytest tests/unit/local_heal/test_receipt_v1_schema.py -q
```

## Test Counts

- `test_output_understanding.py`: 9/9 passed
- `test_receipt_v1_schema.py`: 19/19 passed

## Supported Formats (this phase)

| Format | Enum Value | Behavior |
|--------|------------|----------|
| SEARCH_REPLACE | `SEARCH_REPLACE` | Parses REPLACE block, extracts replacement |
| FENCED_SEARCH_REPLACE | `FENCED_SEARCH_REPLACE` | Unwraps markdown fence, then extracts replacement |
| UNIFIED_DIFF | `UNIFIED_DIFF` | Pass-through as normalized_patch |
| EMPTY_OR_REFUSAL | `EMPTY_OR_REFUSAL` | Fails closed with `failure_reason="empty_or_refusal"` |
| MALFORMED_OUTPUT | `MALFORMED_OUTPUT` | Fails closed with `failure_reason="malformed_output"` |

## Contract Fields

### `CanonicalPatchCandidate`

| Field | Type | Description |
|-------|------|-------------|
| `source_format` | `str` | Detected format enum value |
| `raw_output` | `str` | Original model output |
| `raw_output_hash` | `str` | SHA-256 of raw_output |
| `normalized_patch` | `str` | Canonical text payload after normalization |
| `normalized_patch_hash` | `str` | SHA-256 of normalized_patch (empty if no normalization) |
| `normalization_steps` | `tuple[str, ...]` | Steps applied during normalization |
| `safety_flags` | `tuple[str, ...]` | Safety flags (reserved for future use) |

### `OutputUnderstandingResult`

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether understanding succeeded |
| `candidate` | `CanonicalPatchCandidate \| None` | The candidate (None on failure) |
| `detected_format` | `str` | Detected format enum value |
| `failure_reason` | `str` | Reason for failure (empty on success) |
| `metadata` | `dict[str, Any]` | Reserved for future use |

## Explicit Non-Goals

- No executor integration (local_model_executor.py unchanged)
- No apply/hash truth work (isolated_workspace_apply.py unchanged)
- No route changes
- No committee behavior changes
- No benchmark runner modifications
- No CapabilityPlanner changes
- No cloud fallback integration

## Statements

- Contract-and-parser only
- No executor integration
- No apply/hash truth work
- No route change
- `production_ready=false`
- `public_claim_allowed=false`
