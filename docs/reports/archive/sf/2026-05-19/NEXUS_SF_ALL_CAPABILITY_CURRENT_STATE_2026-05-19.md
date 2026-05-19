# NEXUS SF All Capability Current State

| Capability | State | Primary / best skill | Alternates | Next action |
|---|---:|---|---|---|
| `direct_master_loop` | `runtime_primary` | `sf2-direct_master_loop-route-fit-spec` | - | `keep_runtime_primary` |
| `repair_loop` | `runtime_primary` | `tdd` | - | `keep_runtime_primary` |
| `hyper_sprint` | `runtime_primary` | `sf2-hyper_sprint-route-fit-spec` | - | `keep_runtime_primary` |
| `nightshift` | `runtime_primary` | `sf2-nightshift-route-fit-spec` | - | `keep_runtime_primary` |
| `codeintel` | `runtime_primary` | `sf2-codeintel-route-fit-spec` | - | `keep_runtime_primary` |
| `research` | `catalog_candidate_ready` | `research-citation-chain-verifier` | `sf2-research_control_plane-route-fit-spec`, `research-source-conflict-resolver` | `promotion_review_or_tiebreak` |
| `research_control_plane` | `catalog_candidate_ready` | `research-citation-chain-verifier` | `sf2-research_control_plane-route-fit-spec` | `promotion_review_or_tiebreak` |
| `xray` | `catalog_candidate_ready` | `diagnose` | `sf2-codeintel-route-fit-spec`, `sf2-xray-route-fit-spec` | `promotion_review_or_tiebreak` |
| `learn_ask` | `runtime_primary` | `nexus-capability-upgrade` | - | `keep_runtime_primary` |
| `lancedb` | `catalog_candidate_ready` | `research-source-validation-auditor` | `sf2-lancedb-route-fit-spec`, `nexus-capability-upgrade` | `promotion_review_or_tiebreak` |
| `memory` | `catalog_candidate_ready` | `diagnose` | `sf2-memory-route-fit-spec` | `promotion_review_or_tiebreak` |
| `learning_closure` | `catalog_candidate_ready` | `sf2-learning_closure-route-fit-spec` | `nexus-goal-closure-executor` | `promotion_review_or_tiebreak` |
| `autoreason` | `catalog_candidate_ready` | `sf2-belief-route-fit-spec` | `diagnose`, `sf2-autoreason-route-fit-spec`, `nexus-benchmark-public-report` | `promotion_review_or_tiebreak` |
| `ddtree` | `catalog_candidate_ready` | `nexus-root-cause-probe` | `diagnose`, `sf2-ddtree-route-fit-spec` | `promotion_review_or_tiebreak` |
| `belief` | `runtime_primary` | `sf2-belief-route-fit-spec` | - | `keep_runtime_primary` |
| `autonomic_router` | `catalog_candidate_ready` | `sf2-autonomic_router-route-fit-spec` | `nexus-root-cause-probe`, `diagnose` | `promotion_review_or_tiebreak` |
| `forecast_pregate` | `runtime_primary` | `create-plan` | - | `keep_runtime_primary` |
| `swarm_multi_agent` | `runtime_primary` | `sf2-swarm_multi_agent-route-fit-spec` | - | `keep_runtime_primary` |
| `drone` | `catalog_candidate_ready` | `diagnose` | `nexus-goal-closure-executor`, `sf2-drone-route-fit-spec` | `promotion_review_or_tiebreak` |
| `file_lock_security_gate` | `runtime_primary` | `sf2-file_lock_security_gate-route-fit-spec` | - | `keep_runtime_primary` |
| `mempalace` | `catalog_candidate_ready` | `sf2-mempalace-route-fit-spec` | `acceptance-evidence-failclosed`, `gbrain-soul-audit` | `promotion_review_or_tiebreak` |
| `policy_capability_gate` | `catalog_candidate_ready` | `acceptance-evidence-failclosed` | `cso`, `sf2-policy_capability_gate-route-fit-spec` | `promotion_review_or_tiebreak` |
| `ultra_review` | `catalog_candidate_ready` | `acceptance-evidence-failclosed` | `cso` | `promotion_review_or_tiebreak` |
| `artifact_gate` | `catalog_candidate_ready` | `acceptance-evidence-failclosed` | `nexus-goal-closure-executor`, `research-citation-chain-verifier`, `cso` | `promotion_review_or_tiebreak` |
| `claim_gate` | `runtime_primary` | `nexus-benchmark-continuous-optimization` | - | `keep_runtime_primary` |
| `delivery_acceptance_gate` | `catalog_candidate_ready` | `acceptance-evidence-failclosed` | `sf2-delivery_acceptance_gate-route-fit-spec`, `nexus-goal-closure-executor` | `promotion_review_or_tiebreak` |
| `sandbox_replay` | `catalog_candidate_ready` | `sf2-sandbox_replay-route-fit-spec` | `acceptance-evidence-failclosed`, `diagnose` | `promotion_review_or_tiebreak` |
| `benchmark_meta_opt` | `catalog_candidate_ready` | `nexus-benchmark-continuous-optimization` | `nexus-benchmark-public-report`, `diagnose` | `promotion_review_or_tiebreak` |
| `regression_guard` | `runtime_primary` | `diagnose` | - | `keep_runtime_primary` |
| `registry_skills_sync` | `catalog_candidate_ready` | `sf2-registry_skills_sync-route-fit-spec` | - | `promotion_review_or_tiebreak` |
| `metabolism_resume` | `catalog_candidate_ready` | `nexus-goal-closure-executor` | `setup-matt-pocock-skills`, `diagnose` | `promotion_review_or_tiebreak` |
| `ui_validator` | `catalog_candidate_ready` | `nexus-root-cause-probe` | `sf2-ui_validator-route-fit-spec`, `diagnose` | `promotion_review_or_tiebreak` |
| `external_productivity` | `runtime_primary` | `sf2-external_productivity-route-fit-spec` | - | `keep_runtime_primary` |

## New Skill Update Flow

1. Ingest or materialize the skill source; never runtime-mount directly.
2. Classify source status and quarantine noncanonical/noisy copies.
3. Map the skill into capability buckets using route taxonomy and evidence hints.
4. Build Flash+Nexus no-skill vs candidate skill matrix.
5. Run full preflight, then chunked live fail-fast.
6. Rank effective candidates by receipt validity first, then token delta, then wall delta.
7. Write `(capability, skill_id)` catalog verdict with receipt/evidence paths.
8. Only token-clean, receipt-backed winners enter runtime promotion review.
9. Apply runtime primary only through apply gate plus post-apply smoke.
10. Append replacement ledger and learning closure.
