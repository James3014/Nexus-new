# P2 Apply Hash Anchor Truth Report

## Status
**P2_APPLY_HASH_ANCHOR_TRUTH_PASS**

## Files Changed
- `nexus/services/local_heal/output_understanding.py`
- `nexus/services/local_heal/protocol.py`
- `tests/unit/local_heal/test_output_understanding.py`
- `tests/unit/local_heal/test_apply_hash_anchor_truth.py`

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/output_understanding.py nexus/services/local_heal/protocol.py nexus/services/local_heal/isolated_workspace_apply.py nexus/services/local_heal/isolated_local_solve_loop.py nexus/services/local_heal/local_model_executor.py

python3 -m pytest tests/unit/local_heal/test_output_understanding.py tests/unit/local_heal/test_apply_hash_anchor_truth.py tests/unit/local_heal/test_protocol.py -q

python3 -m pytest tests/unit/local_heal -k "output_understanding or protocol or hash or anchor or apply" --ignore=tests/unit/local_heal/test_decoupled_architecture_tdd.py --ignore=tests/unit/local_heal/test_localheal_pipeline_seam_truth.py --ignore=tests/unit/local_heal/test_qwen_backend_seam.py -q
```

## Test Counts
- `test_output_understanding.py`: 15 passed
- `test_apply_hash_anchor_truth.py`: 32 passed
- `test_protocol.py`: 19 passed
- **Total**: 66 passed (targeted tests)
- **Broader suite**: 298 passed, 2 failed (pre-existing rank_bm25 module missing)

## Output Formats Covered
1. SEARCH_REPLACE
2. FENCED_SEARCH_REPLACE
3. UNIFIED_DIFF
4. PARTIAL_DIFF
5. LINE_SPAN_EDIT
6. FUNCTION_REPLACEMENT
7. NATURAL_LANGUAGE_REPAIR_INTENT (fails closed)
8. EMPTY_OR_REFUSAL (fails closed)
9. MALFORMED_OUTPUT (fails closed)

## Hash-Chain Fields Added or Verified
- `raw_output_hash`: Derived from original model output
- `normalized_patch_hash`: Derived from normalized candidate patch representation (always computed)
- `applied_patch_hash`: Derived from actual workspace diff or applied patch content
- `applied_patch_hash` field added to `CanonicalPatchCandidate`
- `claim_eligible` field added to `CanonicalPatchCandidate`

## Claim Boundary Behavior
- `claim_eligible=false` if raw/normalized/applied hash chain is incomplete
- `claim_eligible=false` if selected candidate does not match applied patch
- `public_claim_allowed=false` by default in `IsolatedApplyReceipt` and `CandidateIsolationReceipt`
- `production_ready=false` by default

## Selected Candidate → Applied Patch Proof
- `selected_candidate_hash_matches_applied` must be true before `solved` can be true
- Verifier pass + hash mismatch does not become solved
- Hash mismatch produces `isolation_applied_hash_mismatch` state
- `CandidateIsolationReceipt` validation blocks on hash mismatch

## Known Residual Debt
1. Pre-existing test failures in `test_local_model_executor.py` and `test_localheal_pipeline_seam_truth.py` due to missing `rank_bm25` module (not caused by P2 changes)
2. `FUNCTION_REPLACEMENT` format detection requires function with return/raise/pass statement
3. `NATURAL_LANGUAGE_REPAIR_INTENT` detection requires specific keywords

## Statements
- ✅ No P3 cloud_with_local_assist implemented
- ✅ No routing behavior changed
- ✅ No solve-rate claim
- ✅ public_claim_allowed=false
- ✅ production_ready=false
