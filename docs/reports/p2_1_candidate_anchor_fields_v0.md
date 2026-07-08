# P2-1 Candidate Anchor Fields

## Status

`P2_1_CANDIDATE_ANCHOR_FIELDS_PASS`

## Summary

Added anchor fields (`target_file`, `target_symbol`, `line_span`, `old_block_hash`) to `CanonicalPatchCandidate` with empty string defaults. Created `enrich_candidate_with_anchor()` to fill them. Wired enrichment in executor after `understand_output()`.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/output_understanding.py` | Modified — added 4 anchor fields + `enrich_candidate_with_anchor()` |
| `nexus/services/local_heal/local_model_executor.py` | Modified — wired enrichment after `understand_output()` |
| `tests/unit/local_heal/test_output_understanding.py` | Modified — added 5 P2-1 tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/output_understanding.py nexus/services/local_heal/local_model_executor.py
pytest tests/unit/local_heal/test_output_understanding.py -v -q
```

## Test Counts

- `test_output_understanding.py`: 14/14 passed (9 original + 5 P2-1)

## Fields Added to CanonicalPatchCandidate

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_file` | `str` | `""` | Target file path |
| `target_symbol` | `str` | `""` | Target symbol name |
| `line_span` | `str` | `""` | Format: `"L<start>-L<end>"` or empty |
| `old_block_hash` | `str` | `""` | SHA-256 of locked_search/search block |

## Function Signature

```python
def enrich_candidate_with_anchor(
    candidate: CanonicalPatchCandidate,
    *,
    target_file: str = "",
    target_symbol: str = "",
    line_span: str = "",
    old_block_hash: str = "",
) -> CanonicalPatchCandidate:
```

## Enrichment Wiring in Executor

After `understand_output()` call (line ~2493) and before projection logic (line ~2505):
- If `_understanding.candidate` is not None, call `enrich_candidate_with_anchor()`
- Pass `request.target_file`, `request.route_context.get("target_symbol", "")`, `source_anchor_hash`
- `line_span` left empty (future task)

## Explicit Statements

- No receipt schema change
- No hash chain enforcement yet
- No `claim_eligible` change
- Not P2 complete
- `public_claim_allowed=false`
- `production_ready=false`
