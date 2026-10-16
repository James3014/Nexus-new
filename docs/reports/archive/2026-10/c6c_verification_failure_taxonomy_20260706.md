# C6C Verification Failure Taxonomy Report

**status**: C6C_VERIFICATION_FAILURE_TAXONOMY_PASS
**date**: 2026-07-06

## Evidence Map

| Subclass | Evidence Rules | Example |
|---|---|---|
| `assertion_or_behavior_mismatch` | stdout contains `EVIDENCE:` and `EXPECTED:` | A3, A4, A5, A6, B1, B3, B4 |
| `wrong_location_or_target_miss` | stdout contains `not found` or `does not exist` | B2, four-model |
| `partial_fix` | Multiple `EVIDENCE:` lines in stdout | — |
| `no_effect_or_noop` | `NO_EFFECTIVE_CHANGE` failure class | — |
| `regression_introduced` | `FAIL` in stdout but no `EVIDENCE:` lines | — |
| `insufficient_evidence_unclassified` | Empty stdout/stderr | — |

## Tests

5 new tests added:

1. `test_verification_failed_rows_split_into_actionable_subclasses` — all rows classifiable
2. `test_apply_success_verifier_fail_not_collapsed_with_no_blocks_found` — no_blocks_found separate
3. `test_failure_subclass_uses_existing_evidence_fields_only` — no new fields required
4. `test_unclassified_bucket_used_when_evidence_is_insufficient` — fallback works
5. `test_current_proof_report_surfaces_top_verification_failed_subclasses` — report surfaces counts

## Taxonomy (Current-Proof)

| Subclass | Count | Combinations | % |
|---|---|---|---|
| `assertion_or_behavior_mismatch` | 7 | A1, A3, A4, A5, A6, B1, B3, B4 | 70% |
| `wrong_location_or_target_miss` | 2 | B2, four-model | 20% |
| `insufficient_evidence_unclassified` | 1 | — | 10% |
| **Total** | **10** | | **100%** |

## Next Target

**`assertion_or_behavior_mismatch`** (70% of verification failures).

The model generates patches that apply correctly, but the patch content doesn't fix the actual bug. The verifier sees the expected behavior in `EXPECTED:` but the patch doesn't produce it.

This is a model capability issue — the model understands what needs to be fixed but produces incorrect code.

## Statements

- **Taxonomy uses existing evidence fields only**: No new API or receipt fields required.
- **no_blocks_found is separate**: Not collapsed with verifier failures.
- **Unclassified bucket exists**: For cases with insufficient evidence.
- **No route change**: Only classification logic added.
- **No production claim**: Only taxonomy established.
