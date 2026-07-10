# L3-E: SHEPHERD Real Sub-Agent Registry

**Status**: L3_E_REAL_SHEPHERD_SUPERVISOR_PASS

## Files changed
- `nexus/orchestrator/sub_agent.py` —新建: `SubAgent` + `SubAgentRegistry` class
- `nexus/orchestrator/shepherd_supervisor.py` — `fork()` 從 registry 抓 `old_definition`；`observe()` / `replay_to()` registry-aware
- `tests/orchestrator/test_shepherd_supervisor.py` — 新增 5 個 L3-E 測試

## Test counts
- 5 new (L3-E) + 5 existing = 10 total PASS

## Changes
1. `SubAgent` dataclass — definition / last_action / trace_history
2. `SubAgentRegistry` — register / get / list_ids
3. `ShepherdSupervisor.__init__` — 可選注入 registry
4. `fork()` — 從 registry 抓既有 definition 填入 `old_definition`
5. `observe()` / `replay_to()` — registry-aware lookup

## Governance boundary
- registry 為可選注入（預設新建空 registry）
- 無 registry 時 `old_definition=""`（向後相容）
