# N30R-R2 Closeout: Four-Task Real Production Path Replay

**Status**: N30R_R2_REAL_CORE_SMOKE_PASS

## run ID
20260710T100200Z

## baseline SHA
884c37f227e95e52bf2891f737f5532511635f62

## R1 wiring commit
bc3cf3dba

## model and provider
qwen2.5-coder:7b-instruct via ollama

## 8-row execution path table

| Task | Arm | Terminal | exec_path | planner | wall |
|------|-----|----------|-----------|---------|------|
| syntax | bare | VERIFIED_FAIL | bare_direct_provider | false | 1.66s |
| syntax | core | VERIFIED_FAIL | nexus_production_localheal_pipeline | true | 1.41s |
| anchor | bare | VERIFIED_FAIL | bare_direct_provider | false | 1.51s |
| anchor | core | VERIFIED_FAIL | nexus_production_localheal_pipeline | true | 1.80s |
| semantic | bare | VERIFIED_FAIL | bare_direct_provider | false | 1.46s |
| semantic | core | VERIFIED_FAIL | nexus_production_localheal_pipeline | true | 1.45s |
| multi | bare | VERIFIED_FAIL | bare_direct_provider | false | 2.77s |
| multi | core | VERIFIED_FAIL | nexus_production_localheal_pipeline | true | 2.97s |

## planner-called core rows: 4/4
## LocalModelExecutor core rows: 4/4
## production path count: 4/4
## legacy adapter count: 0/8
## receipt completeness: 8/8 (100%)
## trust mismatch: 0/8
## terminal status: 8 VERIFIED_FAIL, 0 solved
## dominant failure family: SEMANTIC_VERIFIER_FAILURE (model output does not fix bugs)
## old prompt-variant result excluded: yes
## no uplift claim
## production_ready=false
## public_claim_allowed=false
