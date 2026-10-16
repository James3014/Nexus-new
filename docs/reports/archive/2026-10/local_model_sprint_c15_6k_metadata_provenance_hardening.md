# Local Model Nexus Armor — LV6.5 Four-Model Committee Metadata & Provenance Hardening Report

- **Final Status**: `C15_6K_METADATA_PROVENANCE_HARDENING_PASS`
- **Verification Timestamp**: 2026-07-05
- **Topology**: `local_committee_only` (heterogeneous 4 proposers + 1 judge)

---

## 1. Baseline & Context (C15-6H / C15-6J)
- **C15-6H**: Dual committee toy live solve proven.
- **C15-6J**: Four-model provider calls proven, and candidate identity collisions resolved via unique indices and model slugs in `candidate_id`.
- **Pre-requisite check**: The candidate identity unique commit (`fix(localheal): make committee candidate ids model-unique`) is confirmed as successfully merged at the top of the git branch.

---

## 2. What This Task Changes
This task implements and hardens the metadata and provenance contract (Contracts A/B/C) to separate proposer/judge counts, ensure raw candidate hash tracking, and compile a complete candidate-level truth table with rejection reasons and hash sources.

---

## 3. Telemetry Contracts Hardened

### Contract A — Proposer / Judge Count Separation
- We separated `committee_candidate_count` (total candidates) into:
  - `proposer_candidate_count` (number of proposers only)
  - `judge_count` (number of judges only)
- Under a 4-proposer + 1-judge committee, they evaluate as:
  - `committee_candidate_count` = 5
  - `proposer_candidate_count` = 4
  - `judge_count` = 1

### Contract B — Hash Provenance
- Tracked the selected candidate's raw unaligned patch hash under `raw_candidate_hash`.
- Ensured `selected_hash_source` tracks the alignment strategy (`"applied_git_diff"` if matched, otherwise `"unaligned"`).

### Contract C — Candidate-Level Truth Table Completeness
- Expanded each dictionary inside `committee_candidates` to record:
  - `raw_candidate_hash`
  - `selected_candidate_hash`
  - `selected_hash_source`
  - `applied_patch_hash_source`
  - `rejection_reason` (e.g. `"verifier_failed"`, `"patch_empty"`, `"winner_already_selected"`, `"not_selected"`, etc.)

---

## 4. Tests Added (TDD verification)

We added/strengthened the following tests in `tests/unit/local_heal/test_local_model_executor.py`:
1. **RED 1 (Counts)**: `test_committee_candidate_count_distinguishes_proposer_and_judge`
   - Verified that `proposer_candidate_count` is 2 and `judge_count` is 1 for a 3-member committee mock.
2. **RED 2 (Hash Provenance)**: `test_local_committee_records_raw_and_applied_hash_provenance`
   - Verified that `raw_candidate_hash`, `selected_candidate_hash`, `selected_hash_source`, and `applied_patch_hash_source` are recorded correctly.
3. **RED 3 (Truth Table & Rejection Reason)**: `test_local_committee_candidate_truth_table_contains_hash_sources`
   - Verified candidate-level metadata fields and correct `rejection_reason` mapping for both selected and non-selected candidates.

---

## 5. Test Results

- Targeted tests compile & pass:
  ```bash
  tests/unit/local_heal/test_local_model_executor.py::test_local_committee_records_raw_and_applied_hash_provenance PASSED
  tests/unit/local_heal/test_local_model_executor.py::test_committee_candidate_count_distinguishes_proposer_and_judge PASSED
  tests/unit/local_heal/test_local_model_executor.py::test_local_committee_candidate_truth_table_contains_hash_sources PASSED
  ```
- All 30 committee-related unit tests: **30 PASSED** (100% green).

---

## 6. Telemetry JSON Output (Before vs After)

### Before (C15-6J)
```json
{
  "committee_candidate_count": 5,
  "selected_candidate_id": "...",
  "committee_candidates": [
    {
      "candidate_id": "...",
      "role": "judge",
      "expected_model": "...",
      "invoked_model": "...",
      "provider_called": true,
      "candidate_hash": "...",
      "applied_patch_hash": "..."
    }
  ]
}
```

### After (C15-6K)
```json
{
  "committee_candidate_count": 5,
  "proposer_candidate_count": 4,
  "judge_count": 1,
  "raw_candidate_hash": "a8e171d2...",
  "selected_hash_source": "unaligned",
  "committee_candidates": [
    {
      "candidate_id": "...",
      "role": "secondary_proposer",
      "expected_model": "deepseek-coder:6.7b-instruct",
      "invoked_model": "deepseek-coder:6.7b-instruct",
      "provider_called": true,
      "candidate_hash": "a8e171d2...",
      "raw_candidate_hash": "a8e171d2...",
      "selected_candidate_hash": "e3b0c442...",
      "applied_patch_hash": "",
      "selected_candidate_hash_matches_applied": false,
      "selected_hash_source": "none",
      "applied_patch_hash_source": "",
      "apply_status": "",
      "isolated_verifier_result": "not_run",
      "selected": true,
      "winner": true,
      "rejection_reason": "patch_empty"
    }
  ]
}
```

---

## 7. Remaining Limitations
- Real codebase benchmark effectiveness comparisons (e.g. model pass rate vs committee pass rate) are out-of-scope and deferred to sprint `C15-6L`.

---

## 8. Commit Readiness
The changes are isolated to the telemetry dict inside `local_model_executor.py` and the unit test files. No production control flows or public APIs were modified.
Workspaces are ready for minimal staging and commit.
