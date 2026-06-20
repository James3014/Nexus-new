# Source Revision Hygiene Policy — T4.1

**Effective**: 2026-06-18
**Scope**: All Nexus model candidate registry entries and replay operations

## 1. Purpose

Source revision hygiene prevents source-stale / already-patched workspaces from being misclassified as model failures. It ensures that historical clean candidates are preserved even when current workspace source no longer matches the original buggy state.

## 2. Required Source Fields

Every model candidate or replay row must record:

| Field | Description |
|-------|-------------|
| `source_snapshot_hash` | Git HEAD hash at time of first model success |
| `current_source_hash` | Git HEAD hash at time of current check |
| `canonical_span_hash` | Hash of the canonical SEARCH span content |
| `canonical_span_source` | Source of canonical span (locked_search, ast_boundary, unified_diff, any_valid) |
| `buggy_line_hash` | Hash of the buggy line content |
| `source_anchor_status` | anchored, broken, unknown, reconciled |
| `workspace_dirty_at_anchor_time` | Whether workspace had uncommitted changes at anchor time |
| `replay_eligible` | Whether current source allows clean replay |

## 3. Replay Eligibility

A candidate is `replay_eligible=true` ONLY if ALL of the following are true:

1. Target file exists in current workspace
2. Current source hash matches source snapshot hash, OR allowed reconciliation succeeds
3. Canonical SEARCH exists exactly once, OR deterministic disambiguation exists
4. Buggy line exists in source (if required by task definition)
5. Workspace is not pre-patched (git status clean or resettable)
6. `source_anchor_status` = `anchored` or `reconciled`
7. No model-generated SEARCH is used

## 4. Stale Source Handling

If source is already patched or different version:

- Mark `stale_source_anchor` or `historical_clean_candidate`
- Do NOT count as model failure
- Do NOT invalidate historical clean candidate
- Do NOT rerun model-call unless clean source revision is restored
- Do NOT export as current replay success
- Preserve `model_patch_reward=1.0` in historical evidence

## 5. Forbidden Behavior

- Do NOT lower fuzzy threshold globally
- Do NOT use model-generated SEARCH
- Do NOT silently patch a different span
- Do NOT classify source mismatch as `model_semantic_failure`
- Do NOT make public claim from stale replay
- Do NOT count stale replay as current model success
- Do NOT erase historical clean candidate evidence due to source staleness

## 6. Clean-Room Replay Requirement

For future replay operations:

1. Restore exact source snapshot (git checkout to specific hash)
2. Verify source hash matches snapshot
3. Verify canonical SEARCH hash
4. Then replay stored model output or rerun Qwen14B under same prompt contract
5. Keep historical success and current replay evidence separate

## 7. Failure Taxonomy

| Failure Class | Description |
|---------------|-------------|
| `source_stale` | Source has changed since snapshot |
| `already_patched` | Bug fix already applied in current source |
| `different_version` | Current source is different version than snapshot |
| `buggy_line_not_in_current_source` | Expected buggy line not found |
| `canonical_search_not_in_current_source` | Expected SEARCH span not found |
| `source_snapshot_missing` | No snapshot hash recorded |
| `ambiguous_canonical_search` | Multiple possible SEARCH spans |
| `wrong_file_path` | Target file path incorrect |
| `source_anchor_unknown` | Anchor status not yet determined |
