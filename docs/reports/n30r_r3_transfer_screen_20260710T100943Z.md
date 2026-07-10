# N30R-R3 Closeout: Eight-Task Local Armor Transfer Screen

**Status**: N30R_R3_INCONCLUSIVE

## run ID
20260710T100943Z

## task count: 8
## rows: 32 (8 tasks × 2 trials × 2 arms)

## Bare verified solve rows: 0/16
## Real Core verified solve rows: 0/16
## delta: 0
## distinct gained tasks: 0
## distinct regressed tasks: 0

## paired validity
- trust mismatch: 0
- receipt completeness: 32/32 (100%)
- paired coverage: 100%
- planner_called core rows: 16/16
- legacy adapter: 0/32

## dominant failure family
SEMANTIC_VERIFIER_FAILURE — 7B model output does not fix any of the 8 bugs. Both arms produce VERIFIED_FAIL on all 32 rows.

## failure-family distribution by arm
| Family | Bare | Core |
|--------|------|------|
| VERIFIED_FAIL | 16 | 16 |
| VERIFIED_SOLVE | 0 | 0 |

## p50/p95 wall time
- Bare: p50=3.2s, p95=7.3s
- Core: p50=2.0s, p95=4.0s

## claim boundary
- On this 8-task transfer screen, both Bare and Real Core arms achieved 0/16 verified solves.
- The same Qwen 7B model produced identical failure patterns through both execution paths.
- This is INCONCLUSIVE: sample too small, model capacity may be the binding constraint.
- No comparison with old prompt-only smoke.
- No comparison with Gemini/GPT.
- production_ready=false
- public_claim_allowed=false
