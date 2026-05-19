# NEXUS SF Skill Help Confirmation 2026-05-18

## Summary
- `capability_count`: `33`
- `receipt_delivery_help_count`: `33`
- `strong_help_count`: `10`
- `token_improved_count`: `17`
- `wall_improved_count`: `14`
- `both_cost_improved_count`: `10`
- `both_cost_regressed_count`: `12`
- `mixed_cost_count`: `11`
- `runtime_overlay_primary_count`: `0`
- `catalog_only_hold_count`: `33`

## Runtime-expand candidates (strict strong help)
- `belief` -> `sf2-belief-route-fit-spec` token_delta=-3166 wall_delta=-5.4113
- `claim_gate` -> `nexus-benchmark-continuous-optimization` token_delta=-2839 wall_delta=-23.9404
- `direct_master_loop` -> `sf2-direct_master_loop-route-fit-spec` token_delta=-6314 wall_delta=-78.7746
- `external_productivity` -> `sf2-external_productivity-route-fit-spec` token_delta=-1327 wall_delta=-4.2671
- `file_lock_security_gate` -> `sf2-file_lock_security_gate-route-fit-spec` token_delta=-3122 wall_delta=-27.2381
- `hyper_sprint` -> `sf2-hyper_sprint-route-fit-spec` token_delta=-360 wall_delta=-11.9126
- `learn_ask` -> `nexus-capability-upgrade` token_delta=-796 wall_delta=-5.3544
- `nightshift` -> `sf2-nightshift-route-fit-spec` token_delta=-9501 wall_delta=-53.0616
- `regression_guard` -> `diagnose` token_delta=-9784 wall_delta=-33.5622
- `swarm_multi_agent` -> `sf2-swarm_multi_agent-route-fit-spec` token_delta=-2961 wall_delta=-15.5213

## Hold: functional help but cost mixed/regressed
- `artifact_gate` -> `research-citation-chain-verifier` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=4478 wall_delta=22.8367
- `autonomic_router` -> `sf2-autonomic_router-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=5157 wall_delta=24.614
- `autoreason` -> `sf2-autoreason-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-1247 wall_delta=9.5293
- `benchmark_meta_opt` -> `nexus-benchmark-continuous-optimization` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=5185 wall_delta=15.1591
- `codeintel` -> `sf2-codeintel-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-1312 wall_delta=9.142
- `ddtree` -> `sf2-ddtree-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=13497 wall_delta=40.3892
- `delivery_acceptance_gate` -> `sf2-delivery_acceptance_gate-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=1679 wall_delta=-0.6909
- `drone` -> `sf2-drone-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=624 wall_delta=5.42
- `forecast_pregate` -> `sf2-forecast_pregate-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-1554 wall_delta=7.6163
- `lancedb` -> `sf2-lancedb-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=5378 wall_delta=38.7981
- `learning_closure` -> `sf2-learning_closure-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-102 wall_delta=3.519
- `memory` -> `sf2-memory-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=6510 wall_delta=34.0041
- `mempalace` -> `sf2-mempalace-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=8378 wall_delta=17.6422
- `metabolism_resume` -> `setup-matt-pocock-skills` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=116 wall_delta=69.1926
- `policy_capability_gate` -> `sf2-policy_capability_gate-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-41236 wall_delta=14.9209
- `registry_skills_sync` -> `sf2-registry_skills_sync-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=1035 wall_delta=-49.1376
- `repair_loop` -> `test-driven-development` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=562 wall_delta=19.1855
- `research` -> `research-citation-chain-verifier` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-2222 wall_delta=27.3049
- `research_control_plane` -> `sf2-research_control_plane-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=115 wall_delta=-39.1321
- `sandbox_replay` -> `sf2-sandbox_replay-route-fit-spec` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=-2969 wall_delta=4.227
- `ui_validator` -> `sf2-ui_validator-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=3163 wall_delta=14.5879
- `ultra_review` -> `code-review-and-quality` tier=FUNCTIONAL_HELP_COST_MIXED token_delta=1760 wall_delta=-13.2412
- `xray` -> `sf2-xray-route-fit-spec` tier=FUNCTIONAL_HELP_COST_REGRESSED token_delta=3920 wall_delta=21.5001

## Catalog/live mismatches needing reconciliation
- `artifact_gate` SF3=`nexus-goal-closure-executor` live=`research-citation-chain-verifier`
- `autoreason` SF3=`nexus-benchmark-public-report` live=`sf2-autoreason-route-fit-spec`
- `belief` SF3=`sf2-autoreason-route-fit-spec` live=`sf2-belief-route-fit-spec`
- `claim_gate` SF3=`diagnose` live=`nexus-benchmark-continuous-optimization`
- `delivery_acceptance_gate` SF3=`nexus-benchmark-continuous-optimization` live=`sf2-delivery_acceptance_gate-route-fit-spec`
- `direct_master_loop` SF3=`nexus-goal-closure-executor` live=`sf2-direct_master_loop-route-fit-spec`
- `learn_ask` SF3=`notebooklm-context-bridge` live=`nexus-capability-upgrade`
- `metabolism_resume` SF3=`triage` live=`setup-matt-pocock-skills`
- `nightshift` SF3=`sf2-learning_closure-route-fit-spec` live=`sf2-nightshift-route-fit-spec`
- `policy_capability_gate` SF3=`diagnose` live=`sf2-policy_capability_gate-route-fit-spec`
- `regression_guard` SF3=`nexus-benchmark-continuous-optimization` live=`diagnose`
- `research` SF3=`sf2-research_control_plane-route-fit-spec` live=`research-citation-chain-verifier`
- `sandbox_replay` SF3=`sf2-file_lock_security_gate-route-fit-spec` live=`sf2-sandbox_replay-route-fit-spec`
- `ultra_review` SF3=`diagnose` live=`code-review-and-quality`
