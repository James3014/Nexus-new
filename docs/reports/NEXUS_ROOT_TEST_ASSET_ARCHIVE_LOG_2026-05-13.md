# NEXUS Root-level Legacy Test Assets Archive Log (2026-05-13)

## Summary
- Mode: conservative (archive first, then remove from root)
- Archived at:
  - `/Users/jameschen/Workspace/nexus/.nexus/archive/legacy_test_assets_20260513_070702`
- Root cleanup status:
  - `remaining_in_root = 0` for this batch

## Moved items (13)
1. `test-hardening-run`
2. `test-router-integration`
3. `test_patches`
4. `test_anti_fp.py`
5. `test_compactor.py`
6. `test_direct_wipe.py`
7. `test_llm_fallback.py`
8. `test_patch_apply.py`
9. `test_stage2_policy.py`
10. `test_wp4_ingest.py`
11. `test_wp4_memory.py`
12. `test_wp4_optimize.py`
13. `test_wp4_policy.py`

## Archive manifest snapshot
- `test-hardening-run/tracelog.jsonl`
- `test-router-integration/.musestate`
- `test-router-integration/tracelog.jsonl`
- `test_patches/context_compactor.py.patch`
- `test_anti_fp.py`
- `test_compactor.py`
- `test_direct_wipe.py`
- `test_llm_fallback.py`
- `test_patch_apply.py`
- `test_stage2_policy.py`
- `test_wp4_ingest.py`
- `test_wp4_memory.py`
- `test_wp4_optimize.py`
- `test_wp4_policy.py`

## Notes
- Git will show original tracked root paths as deletions unless archive paths are staged in the same commit.
- This report is the canonical pointer to the archive location for future follow-up or permanent pruning.
