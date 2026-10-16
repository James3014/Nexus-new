# M1.4 Committee-to-Repair Seam Audit

**Status**: M1_4_COMMITTEE_TO_REPAIR_SEAM_AUDIT_PASS

## Executive Summary

The `local_committee_only` topology generates and selects candidate patches via
`LocalCommitteeCandidateProvider` + `CandidateDecisionAdapter`, but the execution
path **returns immediately after normalization** without reaching
`isolated_local_solve_loop` or `diff_repair`. The seam break is at
`_normalize_candidate_patch()` when the parser rejects the candidate (e.g.
`REPLACEMENT_MARKDOWN_FENCE`), producing an empty hash.

## Committee Execution Path (Step by Step)

```
local_model_executor.py:303  if execution_topology == "local_committee_only":
  |
  +--> :320  LocalCommitteeCandidateProvider.generate_committee_candidates()
  |          - Iterates proposer_specs + judge_model
  |          - Calls provider.generate() for each role
  |          - Returns list[CandidateEnvelope]
  |
  +--> :336  CandidateDecisionAdapter.select_candidate(candidates)
  |          - Filters out abstained/blocked candidates
  |          - Applies DDTree pruning (if selected)
  |          - Applies Autoreason ranking (if selected)
  |          - Deterministic role priority fallback
  |          - Returns CandidateDecisionResponse
  |
  +--> :345  selected_patch = decision.selected_candidate_patch
  |
  +--> :347  if selected_patch.strip():
  |          +--> :348  _normalize_candidate_patch(request, locked_search, selected_patch)
  |                     |
  |                     +--> :691  Check if already unified diff (--- a/ + +++ b/)
  |                     |          If yes: passthrough
  |                     |
  |                     +--> :700  SolidSearchReplaceProtocol.parse()
  |                     |          |
  |                     |          +--> If REPLACEMENT_MARKDOWN_FENCE:
  |                     |               return ("", {"protocol_parse_failed": True, ...})
  |                     |          |
  |                     |          +--> If PatchError:
  |                     |               return ("", {"protocol_parse_failed": True, ...})
  |                     |          |
  |                     |          +--> If PatchIntent:
  |                     |               Generate unified diff from search->replace
  |
  +--> :349  selected_hash = sha256(selected_patch) or empty_hash
  |
  +--> :412  return LocalModelExecutorResponse(...)
             *** FUNCTION RETURNS HERE ***
             *** NO isolated_local_solve_loop ***
             *** NO diff_repair ***
```

## Where Candidate Becomes Empty Hash

**Location**: `local_model_executor.py:347-351`

```python
selected_patch = decision.selected_candidate_patch   # raw model output
patch_meta = {}
if selected_patch.strip():
    selected_patch, patch_meta = _normalize_candidate_patch(request, locked_search, selected_patch)
    selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest() if selected_patch.strip() else empty_hash
else:
    selected_hash = empty_hash
```

When `_normalize_candidate_patch` returns `("", {...})` due to parser failure,
`selected_patch.strip()` is falsy, so `selected_hash = empty_hash`.

## CandidateDecisionAdapter Selection

The adapter **does select a candidate** when active (non-abstained) proposers
exist. The `selected_by` field is `"candidate_policy"` for the primary proposer.
The selected patch is the raw model output, which may contain markdown fences.

## _normalize_candidate_patch Rejection

When the model outputs:
```python
```python
<<<<<<< REPLACE
print('fixed')
>>>>>>> REPLACE
```
```

The `SolidSearchReplaceProtocol.parse()` detects markdown fences and returns:
```
PatchError(kind=REPLACEMENT_MARKDOWN_FENCE, message="Replacement appears to be natural language")
```

`_normalize_candidate_patch` returns `("", {"protocol_parse_failed": True, "error_kind": "REPLACEMENT_MARKDOWN_FENCE"})`.

## isolated_local_solve_loop Reachability

**NOT REACHED.** The `local_committee_only` branch in `local_model_executor.py`
returns at line 412. `isolated_local_solve_loop` is only called from the
`localheal_pipeline` topology (via `LocalHealPipelineCapabilityExecutor`), which
is a separate code path.

## diff_repair Reachability

**NOT REACHED.** `diff_repair.repair_malformed_diff` is called inside
`isolated_local_solve_loop.py:178`, which is only reachable from the
`localheal_pipeline` topology. The `local_committee_only` path does not import
or call `diff_repair`.

## Test Results

| Test | Result |
|------|--------|
| `test_committee_path_selects_candidate_before_normalization` | PASS |
| `test_committee_parse_failure_blocks_before_isolated_apply` | PASS |
| `test_committee_parse_failure_does_not_reach_diff_repair` | PASS |
| `test_committee_parse_failure_does_not_claim_candidate_isolated` | PASS |
| `test_committee_parse_failure_does_not_claim_solved` | PASS |

**5 passed, 0 failed**

## Recommendation for Existing Seam Reuse Only

The `local_committee_only` topology is a **candidate generation and selection
path only**. It does NOT have a repair/retry/isolated-solve seam. To reuse
existing repair capabilities:

1. **Option A**: After the committee returns a selected candidate, route through
   `isolated_local_solve_loop.run_isolated_local_solve_loop()` to apply, verify,
   and repair the patch. This requires the caller (router/orchestrator) to
   invoke the isolated solve loop after committee selection.

2. **Option B**: Extend the `local_committee_only` branch in
   `local_model_executor.py` to call `isolated_local_solve_loop` before
   returning, similar to how `localheal_pipeline` does it via
   `LocalHealPipelineCapabilityExecutor`.

3. **Option C**: Add a post-normalization fallback in `_normalize_candidate_patch`
   that strips markdown fences before parsing, reducing the parse failure rate.

**Do NOT**: claim committee solving, add new retry logic, or modify parser/verifier.
The seam exists; the task is to connect it to existing repair infrastructure.
