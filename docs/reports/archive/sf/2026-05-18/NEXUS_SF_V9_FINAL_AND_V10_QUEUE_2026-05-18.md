# NEXUS SF V9 Final + Held RCA + V10 Queue

## V9 Formal Overlay
- `runtime_update_allowed`: `true`
- `primary_count`: `14`
- `post_apply_smoke`: `PASS 14/14`

## Held RCA
- `held_count`: `23`
- `high_priority_retest_count`: `7`
- `cost_mixed_count`: `11`
- `cost_regressed_count`: `12`

## V10 Retest Queue
- `artifact_gate` reason=cost_regressed arms=[None, 'research-citation-chain-verifier', 'nexus-goal-closure-executor']
- `autoreason` reason=cost_mixed arms=[None, 'sf2-autoreason-route-fit-spec', 'nexus-benchmark-public-report']
- `codeintel` reason=cost_mixed arms=[None, 'sf2-codeintel-route-fit-spec', None]
- `ddtree` reason=cost_regressed arms=[None, 'sf2-ddtree-route-fit-spec', None]
- `research` reason=cost_mixed arms=[None, 'research-citation-chain-verifier', 'sf2-research_control_plane-route-fit-spec']
- `ui_validator` reason=cost_regressed arms=[None, 'sf2-ui_validator-route-fit-spec', None]
- `ultra_review` reason=cost_mixed arms=[None, 'code-review-and-quality', 'diagnose']
