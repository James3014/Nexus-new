# NEXUS SF Runtime Replacement Declaration V14

## Status
- `REPLACED`: SF V14 runtime overlay is the active replacement artifact once loaded by the runtime environment.
- `runtime_update_allowed=true`
- `sf_runtime_replacement_complete=true`
- `public_benchmark_allowed=false`

## Runtime Load
```bash
export NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V13_2026-05-19.json
export NEXUS_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V13_2026-05-19.json
```

## Primary Skill Mapping
- `artifact_gate` -> `acceptance-evidence-failclosed`
- `autoreason` -> `sf2-belief-route-fit-spec`
- `belief` -> `sf2-belief-route-fit-spec`
- `claim_gate` -> `nexus-benchmark-continuous-optimization`
- `codeintel` -> `sf2-codeintel-route-fit-spec`
- `ddtree` -> `nexus-root-cause-probe`
- `direct_master_loop` -> `sf2-direct_master_loop-route-fit-spec`
- `drone` -> `diagnose`
- `external_productivity` -> `sf2-external_productivity-route-fit-spec`
- `file_lock_security_gate` -> `sf2-file_lock_security_gate-route-fit-spec`
- `forecast_pregate` -> `create-plan`
- `governance_and_trust` -> `acceptance-evidence-failclosed`
- `hyper_sprint` -> `sf2-hyper_sprint-route-fit-spec`
- `lancedb` -> `research-source-validation-auditor`
- `learn_ask` -> `nexus-capability-upgrade`
- `learning_closure` -> `sf2-learning_closure-route-fit-spec`
- `memory` -> `diagnose`
- `metabolism_resume` -> `nexus-goal-closure-executor`
- `nightshift` -> `sf2-nightshift-route-fit-spec`
- `regression_guard` -> `diagnose`
- `repair_loop` -> `tdd`
- `research` -> `research-citation-chain-verifier`
- `research_and_source_discipline` -> `research-citation-chain-verifier`
- `research_control_plane` -> `research-citation-chain-verifier`
- `swarm_multi_agent` -> `sf2-swarm_multi_agent-route-fit-spec`
- `ui_validator` -> `nexus-root-cause-probe`
- `ultra_review` -> `acceptance-evidence-failclosed`
- `xray` -> `diagnose`

## Held Not Applied
- count: `7`
- held items remain outside runtime primary until a later tie-break passes.

## Evidence
- `apply_result`: `docs/reports/NEXUS_SF_RUNTIME_DEFAULT_APPLY_RESULT_V14_2026-05-19.json`
- `overlay`: `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V13_2026-05-19.json`
- `policy_smoke`: `docs/reports/NEXUS_SF_POST_APPLY_POLICY_SMOKE_V13_2026-05-19.json`
- `runtime_receipt_smoke`: `docs/reports/NEXUS_SF_RUNTIME_RECEIPT_SMOKE_V14_2026-05-19.json`
- `replacement_ledger`: `docs/reports/NEXUS_SF_REPLACEMENT_LEDGER_V13_2026-05-19.json`
- `promotion_review`: `docs/reports/NEXUS_SF_RUNTIME_PROMOTION_REVIEW_V13_2026-05-19.json`

## Replacement Rule
New skills must re-enter the same capability bucket, beat the current primary in paired Flash+Nexus vs Flash+Nexus+skill evidence, pass seal and smoke, then append a replacement ledger item. Public benchmark remains a separate lane.
