# P4 Committee as Routed Tool — Closure Report (Corrected)

## Status: ✅ P4_CLOSED after R1-R5 correction

## Original Closure Gaps (discovered during audit)

The initial P4 implementation (I1-I7 commits) had three closure gaps:

1. **`raw_candidates` was hardcoded empty (`raw_candidates = []`)** — `evaluate_and_execute()` never called a committee candidate producer. The P4 pipeline was a scaffold without a real data source.
2. **E2E tests did not prove the winner path** — `test_p4_e2e_hard_full_success` validated P3 stages but never proved `p4_committee_candidate_count > 0` or `p4_winner_found`. Receipt tests used `FakeCtx` (schema-only) instead of real producer-driven execution.
3. **`_check_fail_closed()` only checked `blocked_reason` / `failure_reasons`** — It did not defensively check `apply_status`, `verifier_status`, hash match, or claim gate state. A result with `selected_candidate_apply_status="failed"` but no explicit `failure_reasons` would silently keep `solved_by_committee=True`.

These gaps did NOT make P4 wrong — they made it **unverifiable as closed**. The R1-R5 correction below addresses all three.

## Correction Commits

### Original P4 Commits (unchanged)

| Package | Commit | Description |
|---------|--------|-------------|
| P4-I1 | `d899ff802` | Committee routed-tool contract |
| P4-I2 | `fe7bac1a5` | Activation/suppression gate |
| P4-I3 | `11a48824d` | Candidate adapter to CanonicalPatchCandidate |
| P4-I4 | `1d66c5d82` | Committee invocation from P3 hard-case path |
| P4-I5 | `623cbc413` | Winner reapply + verifier + claim gate |
| P4-I6 | `ab500cd13` | Zero-winner / no-candidate / malformed fail-closed |
| P4-I7 | `7d4f3b241` | E2E route receipt + regression closure |

### Correction Commits (new)

| Package | Commit | Description |
|---------|--------|-------------|
| P4-R1 | `c5be47174` | `CommitteeCandidateProducer` protocol + injectable seam in `evaluate_and_execute()` |
| P4-R2 | `c5be47174` | `_compute_committee_solved()`, flattened receipt fields (`p4_selected_candidate_hash_matches_applied`, `p4_committee_claim_gate_passed`), model source tracking from raw candidates |
| P4-R3 | `c5be47174` | `_check_fail_closed()` hardened: checks `winner_found`, `apply_status`, `verifier_status`, hash match, claim gate |
| P4-R4 | `c5be47174` | Real E2E receipt tests with fake producer (non-FakeCtx); negative cases: malformed, hash mismatch, verifier fail, flag off, medium |
| P4-R5 | `c5be47174` | This corrected closure report |

## Corrected Closure Evidence

### P4-R1: Candidate Producer Seam

- **Protocol**: `CommitteeCandidateProducer` — callable `(CommitteeRoutedToolRequest) -> list[dict]`
- **Seam**: `evaluate_and_execute(request, *, candidate_producer=None)`
- **Fail-closed**: `None` producer → `failure_reasons=["missing_committee_candidate_producer"]`, `solved_by_committee=False`
- **Exception guard**: producer raises → `failure_reasons=["candidate_producer_error: ..."]`, `solved_by_committee=False`
- **Empty guard**: producer returns `[]` → zero-winner fail-closed path
- **Producer tracking fields**: `candidate_producer_present`, `candidate_producer_invoked`, `candidate_producer_name`, `raw_candidate_count`
- **Tests** (in `test_p4_committee_routed_tool_contract.py`):
  - `test_producer_missing_fail_closed` — verified
  - `test_producer_raises_exception_fail_closed` — verified
  - `test_producer_empty_candidates_fail_closed` — verified
  - `test_producer_missing_excluded_when_gate_blocks` — verified
  - `test_producer_fields_in_receipt` — verified

### P4-R2: Winner Path Solved Computation

- **`_compute_committee_solved()`**: single function checking `apply_result.applied`, `apply_result.hash_matches`, `verifier_result.status == "pass"`, `claim_gate_passed`
- **Flattened receipt fields**: `p4_selected_candidate_hash_matches_applied` and `p4_committee_claim_gate_passed` are now top-level in `receipt_fragment` (not nested inside `claim_decision`)
- **Model source fix**: `selected_candidate_source_model` now reads from raw candidate's `model`/`model_name` field, not from `winner.source_format`
- **Tests** (in `test_p4_committee_real_winner_path.py`):
  - `test_valid_candidate_winner_path_success` — all conditions pass → solved
  - `test_apply_fail_no_solved` — apply blocked → not solved
  - `test_verifier_fail_no_solved` — verifier fails → not solved
  - `test_hash_mismatch_no_solved` — SEARCH/REPLACE hash mismatch → not solved
  - `test_claim_gate_fail_no_solved` — missing source_hash → not solved
  - `test_winner_source_model_from_raw_candidate` — model name correctly tracked
  - `test_mutation_not_allowed_fail_closed` — mutation blocked → not solved
  - `test_selection_strategy_recorded` — first valid selected

### P4-R3: Fail-Closed Guard Hardening

- `_check_fail_closed()` now checks ALL of:
  - `blocked_reason` or `failure_reasons` (existing)
  - `winner_found` is False (new)
  - `selected_candidate_apply_status` != "applied" (new)
  - `selected_candidate_verifier_status` != "pass" (new)
  - `p4_selected_candidate_hash_matches_applied` is False (new)
  - `p4_committee_claim_gate_passed` is False (new)
- **Tests** (in `test_p4_committee_fail_closed.py`):
  - `test_apply_fail_solved_false` — now asserts `solved_by_committee=False` (was `True` before hardening, documenting the gap)
  - `test_fail_closed_catches_verifier_status_without_failure_reasons` — status-based catch
  - `test_fail_closed_catches_hash_mismatch_without_failure_reasons` — status-based catch
  - `test_fail_closed_catches_claim_gate_without_failure_reasons` — status-based catch
  - `test_fail_closed_winner_not_found_without_failure_reasons` — status-based catch
  - `test_fail_closed_all_good_does_not_override` — no false positive

### P4-R4: Real E2E Receipt Tests

Replaced the `FakeCtx`-based closure test with real producer-driven tests:

- `test_p4_e2e_receipt_full_success` — asserts all fields from actual execution:
  - `p4_candidate_producer_present=True`, `p4_candidate_producer_invoked=True`
  - `p4_raw_candidate_count >= 1`, `candidate_count >= 1`, `canonical_candidate_count >= 1`
  - `p4_winner_found=True`, `selected_candidate_apply_status="applied"`
  - `selected_candidate_verifier_status="pass"`, `p4_selected_candidate_hash_matches_applied=True`
  - `p4_committee_claim_gate_passed=True`, `solved_by_committee=True`
  - `p4_fail_closed` is not True
- `test_p4_e2e_malformed_only_fail_closed` — malformed → fail closed
- `test_p4_e2e_hash_mismatch_fail_closed` — hash mismatch → fail closed
- `test_p4_e2e_verifier_fail_closed` — verifier fail → fail closed
- `test_p4_e2e_flag_off_not_invoked` — flag off → not invoked
- `test_p4_e2e_medium_not_invoked` — medium difficulty → not invoked
- `test_p4_receipt_schema_fields_present` — FakeCtx retained as schema-only test (not closure proof)

## Files Modified in Correction

| File | Changes |
|------|---------|
| `nexus/services/local_heal/committee_routed_tool.py` | Added `CommitteeCandidateProducer` protocol, producer fields on `Result`, `_compute_committee_solved()`, hardened `_check_fail_closed()`, flattened receipt fields, model source tracking |
| `nexus/services/local_heal/local_model_executor.py` | `_try_invoke_p4_committee()` accepts `candidate_producer` parameter, passes to `evaluate_and_execute()` |
| `nexus/services/local_heal/receipt.py` | Added `p4_candidate_producer_present`, `p4_candidate_producer_invoked`, `p4_candidate_producer_name`, `p4_candidate_producer_error`, `p4_selected_candidate_hash_matches_applied` fields |
| `tests/unit/local_heal/test_p4_committee_routed_tool_contract.py` | Added 5 producer seam tests + updated receipt fragment + env fixture |
| `tests/unit/local_heal/test_p4_committee_fail_closed.py` | Updated `test_apply_fail_solved_false` to assert `False`; added 6 new hardening tests |
| `tests/unit/local_heal/test_p4_committee_real_winner_path.py` | New — 13 winner path tests covering `_compute_committee_solved()` + E2E winner path |
| `tests/contracts/test_p4_committee_routed_tool_receipts.py` | Replaced FakeCtx closure test with real producer-driven E2E; added 5 negative E2E cases |

## Test Totals After Correction

| Package | Tests | Status |
|---------|-------|--------|
| P4-I1 (contract) | 15 | ✅ Passed |
| P4-I2 (activation gate) | 12 | ✅ Passed |
| P4-I3 (candidate adapter) | 12 | ✅ Passed |
| P4-I4 (invocation from P3) | 7 | ✅ Passed |
| P4-I5 (winner reapply) | 8 | ✅ Passed |
| P4-I6 (fail-closed) | 15 | ✅ Passed |
| P4-R2 (real winner path) | 13 | ✅ Passed |
| P4-I7/R4 (E2E receipts) | 11 | ✅ Passed |
| **P4 Total** | **93** | **✅ 0 failed** |
| P3 Total | 50 | ✅ 0 failed |
| **P3+P4 Total** | **143** | **✅ 0 failed** |

## Verification Commands

```bash
# Focused P4 tests
python3 -m pytest \
  tests/unit/local_heal/test_p4_committee_routed_tool_contract.py \
  tests/unit/local_heal/test_p4_committee_activation_gate.py \
  tests/unit/local_heal/test_p4_committee_candidate_adapter.py \
  tests/unit/local_heal/test_p4_committee_invocation_from_p3.py \
  tests/unit/local_heal/test_p4_committee_winner_reapply_claim_gate.py \
  tests/unit/local_heal/test_p4_committee_fail_closed.py \
  tests/unit/local_heal/test_p4_committee_real_winner_path.py \
  tests/contracts/test_p4_committee_routed_tool_receipts.py -q

# P3 regression
python3 -m pytest \
  tests/unit/local_heal/test_p3_cloud_local_assist_shadow.py \
  tests/engine/test_p3_difficulty_router.py \
  tests/unit/local_heal/test_p3_stage1_local_diagnosis.py \
  tests/unit/local_heal/test_p3_stage2_cloud_candidate_seam.py \
  tests/unit/local_heal/test_p3_stage3_local_cheap_verifier.py \
  tests/unit/local_heal/test_p3_stage4_local_retry.py \
  tests/unit/local_heal/test_p3_stage5_escalation_stub.py \
  tests/contracts/test_p3_end_to_end_receipts.py -q
```

Both return 0 failures.

## Final P4 Complete Conditions

- [x] CommitteeCandidateProducer protocol + injectable seam
- [x] Gate allowed + producer missing → fail closed
- [x] Producer raises → fail closed
- [x] Producer returns empty → zero-winner fail closed
- [x] Candidate canonicalization via CanonicalPatchCandidate
- [x] Winner selection (first valid, no diversity)
- [x] Winner isolated workspace apply
- [x] Verifier checks applied file
- [x] `_compute_committee_solved()` uses apply/verifier/hash/claim gate
- [x] Flattened receipt fields (hash_matches_applied, claim_gate_passed)
- [x] Winner source model tracked from raw candidate
- [x] `_check_fail_closed()` checks all 5 conditions
- [x] Zero-winner fail closed
- [x] Missing proposer/judge fail closed
- [x] E2E receipt tests use real producer (not FakeCtx for closure)
- [x] Negative E2E: malformed, hash mismatch, verifier fail, flag off, medium
- [x] Receipt records full P4 path including producer fields
- [x] P3 regression green
- [x] Committee only enters from P3 hard_case_escalation_stub
- [x] Committee is NOT default solve topology

## P5/P6

Deferred. Not started.
