# M1: Learning Loop Write Endpoint in Main Router

**Status**: M1_PASS

## Files changed
- `nexus/core/router.py` — 在 `route_candidates()` 的 learning_closure.jsonl 寫入後, 追加 OutcomeMemoryManager.save_episode_and_tune_sync() 呼叫
- `nexus/learning/outcome_memory.py` — 新建 `build_episode_from_receipts()` helper function
- `tests/unit/local_heal/test_router_learning_loop.py` — 新建: 5 個 M1 test

## Test counts
- 5 new (M1) + 210 existing core tests = 215 total PASS (1 pre-existing unrelated failure)

## Changes
1. `outcome_memory.py:build_episode_from_receipts()` — 從 router 的 receipts/plan/context 建構 EpisodeOutcomeRecord
2. `router.py:321-335` — M1 block: env flag `NEXUS_LEARNING_LOOP_WRITE_ENABLED` (預設 1), try/except 不阻擋主路由

## Governance boundary
- env flag `NEXUS_LEARNING_LOOP_WRITE_ENABLED=0` 可關閉
- OutcomeMemoryManager 拋 exception 不阻擋主路由
- 不修改 learning_closure.jsonl 寫入邏輯
