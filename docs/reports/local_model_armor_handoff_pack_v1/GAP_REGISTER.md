# Gap Register

## P0 Gaps (Blockers)

| Gap | Evidence | Blocker? | Next Micro-Task |
|-----|----------|----------|-----------------|
| rank_bm25 module missing | test_localheal_pipeline_seam_truth.py failures | Yes (for pipeline tests) | `pip install rank_bm25` or mock in tests |
| Real provider smoke not executed | SKIPPED in test_local_model_executor_planner_path.py | No (env flag required) | Run with explicit env flag when ready |

## P1 Gaps (Important)

| Gap | Evidence | Blocker? | Next Micro-Task |
|-----|----------|----------|-----------------|
| 30 pipeline seam tests fail | test_localheal_pipeline_seam_truth.py | Partial (rank_bm25 dependent) | Install rank_bm25 or update test mocks |
| cloud_with_local_assist uses FakeCloudCandidateProvider | local_model_executor.py L2449 | No (shadow-only by design) | Implement real cloud provider when ready |

## P2 Gaps (Non-blocking)

| Gap | Evidence | Blocker? | Next Micro-Task |
|-----|----------|----------|-----------------|
| P8-E not completed with real network call | P8-E0 reconciliation | No (dry_run accepted) | Execute real network smoke when ready |
| No heldout benchmark receipts | No benchmark artifacts | No | Run heldout benchmarks when ready |

## P3 Gaps (Nice-to-have)

| Gap | Evidence | Blocker? | Next Micro-Task |
|-----|----------|----------|-----------------|
| No comparative benchmark vs Gemini/GPT | No benchmark receipts | No | Add comparative benchmarks |
| No solve-rate evidence | No benchmark receipts | No | Add solve-rate tracking |

## Resolved Gaps

| Gap | Resolution |
|-----|-----------|
| P3 closed as synthetic/dry-run | P3 sealed with synthetic provider trace |
| P6 closed as heldout dry-run | P6 sealed with heldout dry-run evidence |
| P7 closed as synthetic E2E | P7 sealed with synthetic E2E integration |
| P8 dry-run status corrected | P8 sealed as HUMAN_APPROVED_NETWORK_SMOKE_READY |
| public_claim_allowed hardcoded false | Verified in all receipts |
| production_ready hardcoded false | Verified in all receipts |
