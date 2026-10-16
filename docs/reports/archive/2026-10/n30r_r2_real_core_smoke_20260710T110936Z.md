# N30R-R2 Closeout: Four-Task Real Production Path Replay (uv env)

**Status**: N30R_R2_REAL_CORE_SMOKE_PASS

## run ID
20260710T110936Z

## environment
- python: .venv/bin/python3 (3.14.0, uv managed)
- lancedb: 0.30.2
- requests: 2.33.1
- urllib3: 2.5.0
- charset-normalizer: 3.4.7

## 8-row results

| Task | Arm | Terminal | planner | pipe | wall |
|------|-----|----------|---------|------|------|
| syntax | bare | VERIFIED_FAIL | false | false | 5.9s |
| syntax | core | INFRA_INVALID | true | true | 169.8s |
| anchor | bare | VERIFIED_FAIL | false | false | 1.4s |
| anchor | core | INFRA_INVALID | true | true | 76.2s |
| semantic | bare | VERIFIED_SOLVE | false | false | 1.3s |
| semantic | core | INFRA_INVALID | true | true | 113.9s |
| multi | bare | VERIFIED_FAIL | false | false | 5.7s |
| multi | core | INFRA_INVALID | true | true | 188.8s |

## planner-called core rows: 4/4
## pipeline_called core rows: 4/4
## core solved: 0/4 (INFRA_INVALID due to production pipeline timeout)
## bare solved: 1/4 (semantic task)
## trust mismatch: 0
## receipt completeness: 8/8
## production_ready=false
## public_claim_allowed=false
