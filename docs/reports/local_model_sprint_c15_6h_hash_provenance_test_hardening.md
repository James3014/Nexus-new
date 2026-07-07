# Local Model Nexus Armor — LV6 Hash Provenance Test-only Hardening Report

- **Final Status**: `C15_6H_TEST_ONLY_BLOCKED_METADATA_GAP`
- **Verification Timestamp**: 2026-07-05
- **Task Type**: Test-only Hardening (Contract verification)

---

## 0. Claim Boundary Verification

This sprint is strictly **test-only** and **contract hardening**. The boundary for the Local Model Committee is locked at:
`C15_6H_DUAL_COMMITTEE_TOY_LIVE_SOLVE_PROVEN`

This proves the mechanics of the Dual Proposer + Judge vote works on toy tasks under live calls, but does **not** claim real benchmark solve rates or Gemini-equivalent intelligence.

---

## 1. Hardening Contracts

### Contract A — Borda Winner Alignment
- **Requirement**: If Autoreason votes a winner via Borda, it must not be overridden by role priority fallbacks.
- **Test Added**: `test_borda_winner_becomes_selected_candidate` in `test_candidate_decision_adapter.py`
- **Status**: **GREEN (PASS)**
  - Successfully validated sorting is correctly aligned to Borda scores when present, returning `selected_by == "committee_borda_policy"`.

### Contract B — Hash Provenance
- **Requirement**: Telemetry must record `raw_candidate_hash` alongside the adjusted `selected_candidate_hash` (derived from git diff), and track `selected_hash_source == "applied_git_diff"`.
- **Test Added**: `test_local_committee_records_raw_and_applied_hash_provenance` in `test_local_model_executor.py`
- **Status**: **RED (FAIL - METADATA GAP)**
  - Fails on `assert meta.get("raw_candidate_hash") == raw_hash` because the top-level executor output metadata lacks raw candidate tracking fields.

### Contract C — Candidate Counts
- **Requirement**: Explicitly separate proposer candidate count from judge count.
- **Test Added**: `test_committee_candidate_count_distinguishes_proposer_and_judge` in `test_local_model_executor.py`
- **Status**: **RED (FAIL - METADATA GAP)**
  - Fails on `assert meta.get("proposer_candidate_count") == 2` because these segmented fields do not exist yet in the metadata payload.

---

## 2. Metadata Gaps & Minimal Patch Proposal

To transition the RED tests to GREEN, we require approval for the following minimal patch in `local_model_executor.py`:

```python
# Proposed additions inside LocalModelExecutor raw_meta assembly:
# 1. Proposer & Judge Counts
proposers = [c for c in candidates if c.role != "judge"]
judges = [c for c in candidates if c.role == "judge"]
raw_meta["proposer_candidate_count"] = len(proposers)
raw_meta["judge_count"] = len(judges)

# 2. Hash Provenance tracking
selected_cand_obj = next((c for c in candidates if c.candidate_id == decision.selected_candidate_id), None)
if selected_cand_obj:
    raw_hash = selected_cand_obj.candidate_patch_hash if hasattr(selected_cand_obj, "candidate_patch_hash") else getattr(selected_cand_obj, "patch_sha256", "")
    raw_meta["raw_candidate_hash"] = raw_hash
    raw_meta["selected_hash_source"] = "applied_git_diff" if hash_match else "unaligned"
```

This patch is 100% telemetry-only (zero runtime side-effects) and has a blast radius of **zero**.

---

## 3. What Remains Unproven
- Real benchmark solve rates on complex code-bases (e.g. `astropy`) under multi-model committees.
- Statistical verification of committee voting accuracy over a large task sample.
