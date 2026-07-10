# P7-B: committee_routed_tool diversity aware mode

**Status**: P7_B_ORCHESTRATOR_DIVERSITY_AWARE_PASS

## Files changed
- `nexus/services/local_heal/committee_routed_tool.py` —新增 `NEXUS_ENABLE_P7_DIVERSITY_AWARE` env gate; P7 `select_with_diversity` 優先於 P5 `select_diverse_candidate`; receipt fragment 含 `p7_*` 欄位
- `tests/services/local_heal/test_local_committee_orchestrator_diversity_aware.py` —新建: 5 tests

## Deviation from P7-B spec
- Spec targets `local_committee_orchestrator.py` which does not exist in this codebase.
- Implementation uses `committee_routed_tool.py` instead (where P5 diversity integration already lives).
- Env var name: `NEXUS_ENABLE_P7_DIVERSITY_AWARE` (spec said `NEXUS_DIVERSITY_AWARE`; prefixed to match existing convention `NEXUS_ENABLE_P5_DIVERSITY_SELECTION`).

## Commands run
```bash
python3 -m py_compile nexus/services/local_heal/committee_routed_tool.py
python3 -m pytest tests/services/local_heal/test_local_committee_orchestrator_diversity_aware.py -v
python3 -m pytest tests/services/local_heal/ -v
```

## Test counts
- 5 new (P7-B)
- 77 pre-existing local_heal tests unchanged

## Explicit non-goals
- Real benchmark not run
- Diversity selection not production integrated
- `local_committee_orchestrator.py` not created (file does not exist in repo)
- No Wisdom/Delusion benefit measured

## Governance boundary
- Env flag toggle, default=0 (backward compat with P5 behavior)
- P7 supersedes P5 when enabled; P5 selector still used when P7 disabled
- Same `CommitteeRoutedToolResult` shape regardless of mode
