# Nexus Skill-Fit Milestone Task Cards 2026-05-16

## Goal Contract

- **Goal**: Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus should approach GPT-5.5 direct verified delivery on fixed commercial-model-basis public tasks, with trust mismatch 0, audit-ready evidence, and sustainable always-on cost.
- **Boundary**: Skill-fit lanes are diagnostic and promotion-supporting. They are not public commercial claim denominators.
- **Spec Kit status**: `specify` is available as a contract-shaping tool, but `.specify` must not be initialized in the current dirty worktree.

## Milestone Roadmap

1. **4R Flash180 Skill-Fit Rerun**: rerun the repaired expanded skill-fit matrix after local workspace task filtering.
2. **5R Catalog Promotion Draft**: produce receipt-backed `(capability, skill_id)` default/alternate/needs_more_data/reject mapping without runtime auto-update.
3. **5R-R1 Targeted Replay Controller**: replay only queued `needs_more_data` skill arms after capability-only sweep, without rerunning rejected arms.
4. **5R-R2 Promotion Threshold Contract**: freeze the evidence threshold for `needs_more_data -> alternate/default` while `runtime_update_allowed=false`.
5. **6R Multi-Capability Ablation Hooks**: expand beyond `repair_and_coding` while preserving capability-specific verdicts.
6. **7R Flash100 Route-Cost Regression**: run only after at least one `(capability, skill_id)` reaches alternate/default readiness; verify lower cost does not reduce capability.
7. **8R Pro18 Sanity**: run only after Flash100 route-cost regression is clean; use Pro as provider sanity, not skill-fit debugging.
8. **9 GPT-5.5 Paired Baseline**: run only after Flash/Pro lanes are gate-clean and commercial-model-basis ready.

## Task Card 4R: Flash180 Skill-Fit Rerun

- **Scope**: Run `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_REPAIR_AND_CODING_FLASH180_2026-05-16.json` end to end.
- **Exit condition**: `180/180` rows completed, run status `PASS`, trust mismatch 0, negative controls fully blocked, catalog `matrix_complete=true`.
- **Fail-fast**: Stop on any delivery RETURN, trust mismatch, negative control not blocked, missing receipt/evidence path, or local workspace task in matrix.
- **Evidence refs**: `/private/tmp/nexus_skill_fit_flash180_live_rerun_20260516/live_summary.json`, `docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_FLASH180_RERUN_2026-05-16.json`.
- **Do not**: Treat Flash180 as public claim evidence or runtime promotion by itself.

## Task Card 5R: Catalog Promotion Draft

- **Scope**: Convert the Flash180 catalog into a non-runtime promotion draft grouped by `(capability, skill_id)`.
- **Exit condition**: Each `keep`, `replace_candidate`, `needs_more_data`, and `reject` verdict has evidence refs and receipt refs; `runtime_update_allowed=false`.
- **Fail-fast**: Any positive verdict without evidence or receipt returns; any incomplete matrix returns.
- **Evidence refs**: `nexus.capability_skill_promotion_policy_draft.v1` artifact generated from the Flash180 catalog.
- **Do not**: Write promoted runtime defaults before Flash100/Pro gates.

## Task Card 6R: Multi-Capability Ablation Hooks

- **Scope**: Extend the same ablation contract to `repair_and_coding`, `governance_and_trust`, and `research_and_source_discipline`.
- **Exit condition**: Each capability has capability-only, primary skill, alternate skill, and wrong/quarantined control arms; catalog verdicts remain capability-specific.
- **Fail-fast**: Any skill verdict keyed only by `skill_id`, any selected-only success claim, or any wrong/quarantined skill passing.
- **Evidence refs**: multi-capability matrix and catalog under `docs/reports/`.
- **Do not**: Create a global skill router that overrides the capability planner.

## Task Card 5R-R1: Targeted Replay Controller

- **Scope**: Encode stable discovery as `capability_sweep -> targeted_replay -> full_seal`, where targeted replay derives row ids from the rerun queue.
- **Exit condition**: `capability_sweep` can run only `capability_only`; `targeted_replay` can run only queued `needs_more_data` skill rows; `full_seal` remains the only complete matrix evidence.
- **Fail-fast**: Missing rerun queue, empty queued row match, wrong/quarantined row entering targeted replay, or RETURN row without `failure_action`.
- **Evidence refs**: `run_discovery_controller`, `select_skill_discovery_replay_row_ids`, and preflight summaries under `/private/tmp/nexus_skill_fit_*controller*`.
- **Do not**: Treat targeted replay as a replacement for full sealing evidence.

## Task Card 5R-R2: Promotion Threshold Contract

- **Scope**: Freeze the threshold for promotion draft escalation from `needs_more_data` to `alternate/default`.
- **Exit condition**: Promotion requires complete matrix evidence, trust mismatch 0, evidence refs, receipt refs, repeated denominator, and at least one later Flash50/100 validation gate.
- **Fail-fast**: Any promotion without receipt/evidence path, any runtime update attempt from discovery lane, or any denominator drift.
- **Evidence refs**: promotion draft plus rerun queue artifacts under `docs/reports/`.
- **Do not**: Automatically update runtime defaults from a single Flash180 diagnostic run.

## Task Card 7R: Flash100 Route-Cost Regression

- **Scope**: Run Flash100 on the keep/alternate mapping candidate produced by 5R/6R.
- **Exit condition**: verified delivery does not drop, trust mismatch remains 0, route evidence is complete, token/wall/model-call ledger is conserved, and cost improvement is separated from delivery claims.
- **Fail-fast**: Any missing provider token ledger, suspicious zero-fill, trust mismatch, or skill evidence gap.
- **Evidence refs**: route-stability validation report and cost ledger under `.nexus/reports/`.
- **Do not**: Optimize by deleting evidence, verifier, or governance gates.

## Task Card 8R: Pro18 Sanity

- **Scope**: Run 18-task Gemini 3.1 Pro sanity only after Flash100 is clean.
- **Exit condition**: Pro follows the same taskset/verifier/disclosure rules; no skill-fit-only artifact is used as public basis.
- **Fail-fast**: Provider model lock missing, hidden verifier disabled, commercial basis not ready, or direct/with-arm boundary contaminated.
- **Evidence refs**: Pro18 evidence bundle and promotion-readiness summary under `.nexus/reports/`.
- **Do not**: Use Pro to debug a Flash skill-fit failure.

## Current Stop Rule

- If 4R fails, stop before 5R-8R, classify the failure, patch the smallest responsible hook, write the lesson, and rerun the narrow gate before continuing.

## 2026-05-16 Execution Update

- **4R status**: PASS. `rerun16` completed `180/180` rows with `return_count=0`.
- **4R evidence**: `/private/tmp/nexus_skill_fit_flash180_live_rerun16_20260516/live_summary.json` and `docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_FLASH180_RERUN16_2026-05-16.json`.
- **5R status**: PASS as draft only. Promotion policy was generated without runtime update.
- **5R evidence**: `docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_REPAIR_AND_CODING_FLASH180_2026-05-16.json` and `docs/reports/NEXUS_SKILL_DISCOVERY_RERUN_QUEUE_REPAIR_AND_CODING_FLASH180_2026-05-16.json`.
- **5R verdict**: no default or alternate skill yet; `test-driven-development`, `gstack-investigate`, and `aibdd.auto.java.e2e.refactor` are `needs_more_data`; `addy-code-simplification` is `reject`.
- **5R-R1 status**: PASS for controller seam. `run_discovery_controller` now supports `capability_sweep`, `targeted_replay`, and `full_seal`; targeted replay uses the rerun queue to select row ids.
- **5R-R1 evidence**: `/private/tmp/nexus_skill_fit_repair_targeted_replay_preflight_20260516/preflight_summary.json`.
- **5R-R1 live status**: PASS as targeted replay, not promotion. The live queued replay completed `90/90` rows with `return_count=0`.
- **5R-R1 live evidence**: `/private/tmp/nexus_skill_fit_repair_targeted_replay_live_20260516/live_summary.json` and `docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_TARGETED_REPLAY_2026-05-16.json`.
- **5R-R2 status**: PASS as threshold contract. `flash100_allowed=false`; no default/alternate candidate exists yet because all three queued skills remain `needs_more_data`.
- **5R-R2 evidence**: `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_REPAIR_AND_CODING_FLASH180_2026-05-16.json` and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_REPAIR_AND_CODING_TARGETED_REPLAY_2026-05-16.json`.
- **6R status**: PASS for hook/preflight readiness, not full live sealing. Machine-readable failure classifier, baseline-first matrix ordering, path-safe candidate relevance, alias dedupe, negative-control mount boundary, long-tail task/category demotion hooks, multi-capability plan/matrix tests, and controller preflight sweeps are implemented.
- **6R evidence**: `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_GOVERNANCE_AND_TRUST_FLASH180_2026-05-16.json`, `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_RESEARCH_AND_SOURCE_DISCIPLINE_FLASH180_2026-05-16.json`, `/private/tmp/nexus_skill_fit_governance_controller_sweep_20260516/preflight_summary.json`, and `/private/tmp/nexus_skill_fit_research_controller_sweep_20260516/preflight_summary.json`.
- **6R-A live status**: PASS. Governance full live sealing resumed from the quota stop and completed `180/180` rows with `return_count=0`.
- **6R-A evidence**: `/private/tmp/nexus_skill_fit_governance_full_live_20260516/live_summary.json`, `docs/reports/NEXUS_SKILL_FIT_CATALOG_GOVERNANCE_AND_TRUST_FULL_LIVE_2026-05-16.json`, `docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_GOVERNANCE_AND_TRUST_FULL_LIVE_2026-05-16.json`, and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_GOVERNANCE_AND_TRUST_FULL_LIVE_2026-05-16.json`.
- **6R-A verdict**: no default or alternate skill yet. `acceptance-evidence-failclosed`, `cso`, and `nexus-root-cause-probe` remain `needs_more_data`; `nexus-acceptance-evidence-gate` is `reject`; `flash100_allowed=false`.
- **6R-B live status**: PASS. Research/source-discipline full live sealing completed the matrix SSOT of `132/132` rows with `return_count=0`.
- **6R-B evidence**: `/private/tmp/nexus_skill_fit_research_full_live_20260516/live_summary.json`, `docs/reports/NEXUS_SKILL_FIT_CATALOG_RESEARCH_AND_SOURCE_DISCIPLINE_FULL_LIVE_2026-05-16.json`, `docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_RESEARCH_AND_SOURCE_DISCIPLINE_FULL_LIVE_2026-05-16.json`, and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_RESEARCH_AND_SOURCE_DISCIPLINE_FULL_LIVE_2026-05-16.json`.
- **6R-B verdict**: research candidates all rejected. `arxiv`, `browserbase-company-research`, `browserbase-search`, and `gbrain-academic-verify` are `reject`; `flash100_allowed=false`.
- **6R-C status**: PASS as RCA. Targeted replay blocked promotion because row delivery passed but skill outcome contribution stayed below `alternate_min_effective_rate=0.6`.
- **6R-C evidence**: `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_RCA_REPAIR_AND_CODING_TARGETED_REPLAY_2026-05-16.json` and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_RCA_MULTI_CAPABILITY_2026-05-16.json`.
- **6R-C current root cause**: `no_receipt_backed_skill_reached_alternate_or_default_threshold_and_research_candidates_all_rejected`.
- **7R status**: BLOCKED. Flash100 route-cost regression is not eligible until at least one skill reaches keep/alternate promotion readiness.
- **8R status**: BLOCKED. Pro18 sanity is not eligible until Flash100 route-cost regression has clean delivery/trust/cost evidence.

## Next Single-Exit Task Cards

### Task Card 6R-D: Governance Targeted Replay or Candidate Pool V2

- **Scope**: Decide whether governance `needs_more_data` rows should get targeted replay, or whether the candidate pool should be refreshed before spending more Flash quota.
- **Exit condition**: either one governance `(capability, skill_id)` reaches alternate/default threshold, or a machine-readable candidate-pool-v2 report replaces low-yield candidates with safer contenders.
- **Fail-fast**: selected-only contribution, missing evidence/receipt path, trust mismatch, or any runtime policy write.
- **Do not**: run Flash100, Pro18, or GPT-5.5 paired baseline from a `needs_more_data` state.

### Task Card 6R-E: Research Candidate Replacement

- **Scope**: Build research/source-discipline candidate pool v2 because the first four candidates were all rejected in full live sealing.
- **Exit condition**: replacement candidates have source receipts, capability relevance, ablation eligibility, and negative-control safety before live spend.
- **Fail-fast**: unpinned external source, reference-only skill promoted to runtime, or global skill verdict not keyed by `(capability, skill_id)`.
- **Do not**: treat rejected research candidates as neutral; they should be skipped until candidate source or taskset changes.

### Task Card 7R: Flash100 Route-Cost Regression

- **Status**: BLOCKED.
- **Unlock condition**: at least one receipt-backed `(capability, skill_id)` has alternate/default recommendation and `flash100_allowed=true` in the threshold contract.

## 2026-05-17 Execution Update

- **6R-D status**: PASS as RCA and targeted replay, not promotion. Row-level RCA selected only `nexus-root-cause-probe` for targeted replay.
- **6R-D evidence**: `docs/reports/NEXUS_SKILL_FIT_ROW_LEVEL_RCA_GOVERNANCE_AND_TRUST_2026-05-17.json`, `docs/reports/NEXUS_SKILL_DISCOVERY_RERUN_QUEUE_GOVERNANCE_AND_TRUST_RCA_TARGETED_2026-05-17.json`, `/private/tmp/nexus_skill_fit_governance_targeted_replay_20260517/live_summary.json`, and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_GOVERNANCE_AND_TRUST_TARGETED_REPLAY_2026-05-17.json`.
- **6R-D verdict**: targeted replay completed `30/30` rows with `return_count=0`, but `nexus-root-cause-probe` remained `needs_more_data` at `15/30`; `flash100_allowed=false`.
- **6R-E status**: PASS as candidate-pool replacement and preflight. Research v2 excluded the four rejected v1 candidates and selected `gbrain-data-research`, `gbrain-perplexity-research`, `gbrain-concept-synthesis`, and `research-paper-writing`.
- **6R-E evidence**: `docs/reports/NEXUS_RESEARCH_CANDIDATE_V2_REPORT_2026-05-17.json`, `docs/reports/NEXUS_RESEARCH_CANDIDATE_POOL_V2_2026-05-17.json`, `docs/reports/NEXUS_SKILL_FIT_ABLATION_PLAN_RESEARCH_AND_SOURCE_DISCIPLINE_V2_2026-05-17.json`, `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FLASH132_2026-05-17.json`, and `/private/tmp/nexus_skill_fit_research_v2_preflight_20260517/preflight_summary.json`.
- **6R-E verdict**: research v2 matrix preflight completed `132/132` rows with `return_count=0`; live Flash spend is now eligible but still diagnostic-only.
- **7R status**: BLOCKED. No default/alternate skill exists yet; do not start Flash100 route-cost regression.
- **Next card**: `6R-F Research V2 Full Live Sealing`, run the v2 matrix live only if Flash quota is available, then rebuild catalog/promotion/threshold contracts.

## 2026-05-17 Execution Update 2

- **6R-F status**: PASS as full live sealing, not promotion. Research v2 live completed `132/132` rows with `return_count=0`.
- **6R-F evidence**: `/private/tmp/nexus_skill_fit_research_v2_full_live_20260517/live_summary.json`, `docs/reports/NEXUS_SKILL_FIT_CATALOG_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json`, `docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json`, `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json`, and `docs/reports/NEXUS_SKILL_FIT_ROW_LEVEL_RCA_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json`.
- **6R-F verdict**: all four research v2 candidates were rejected; `flash100_allowed=false`.
- **6R-G status**: PASS as governance candidate-v2 replacement, preflight, and Flash30 live diagnostic. Selected `cso`, `acceptance-evidence-failclosed`, `claudeosint-safe-surface-audit`, and `gbrain-soul-audit`; live completed `30/30` rows with `return_count=0`.
- **6R-G evidence**: `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_V2_REPORT_2026-05-17.json`, `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_POOL_V2_2026-05-17.json`, `docs/reports/NEXUS_SKILL_FIT_ABLATION_PLAN_GOVERNANCE_AND_TRUST_V2_2026-05-17.json`, `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_GOVERNANCE_AND_TRUST_V2_FLASH30_2026-05-17.json`, `/private/tmp/nexus_skill_fit_governance_v2_preflight_20260517/preflight_summary.json`, `/private/tmp/nexus_skill_fit_governance_v2_flash30_live_20260517/live_summary.json`, and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_GOVERNANCE_AND_TRUST_V2_FLASH30_LIVE_2026-05-17.json`.
- **6R-G verdict**: `acceptance-evidence-failclosed`, `claudeosint-safe-surface-audit`, and `cso` remain `needs_more_data`; `gbrain-soul-audit` is `reject`; `flash100_allowed=false`.
- **7R status**: BLOCKED. Candidate replacement and live sealing are clean, but no capability has alternate/default threshold readiness.
- **Next card**: `6R-H Governance V2 Targeted Replay or Taskset Expansion`, replay only the three queued `needs_more_data` governance v2 candidates or expand governance task diversity before spending more live Flash.
- **6R-H status**: PASS as fail-fast diagnosis and replacement loop. Targeted replay stopped at `3/15` because `claudeosint-safe-surface-audit` hit `skill_stop_loss: timeout_before_receipt`; V2B demoted that skill and selected `cso`, `acceptance-evidence-failclosed`, `multi-agent-handoff-v15-execution-and-validation`, and `self-audit`.
- **6R-H evidence**: `/private/tmp/nexus_skill_fit_governance_v2_targeted_replay_20260517/live_summary.json`, `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_V2B_REPORT_2026-05-17.json`, `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_POOL_V2B_2026-05-17.json`, and `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_GOVERNANCE_AND_TRUST_V2B_FLASH30_2026-05-17.json`.
- **6R-I status**: PASS as long-tail task quarantine. V2B live stopped on capability-only `pub-ref-002` with `task_unstable_long_tail: timeout_before_receipt`; V2C excluded `pub-ref-002`, kept five stable governance tasks, and completed live `30/30` with `return_count=0`.
- **6R-I evidence**: `/private/tmp/nexus_skill_fit_governance_v2b_flash30_live_20260517/live_summary.json`, `docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_GOVERNANCE_AND_TRUST_V2C_FLASH30_2026-05-17.json`, `/private/tmp/nexus_skill_fit_governance_v2c_preflight_20260517/preflight_summary.json`, `/private/tmp/nexus_skill_fit_governance_v2c_flash30_live_20260517/live_summary.json`, and `docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_GOVERNANCE_AND_TRUST_V2C_FLASH30_LIVE_2026-05-17.json`.
- **6R-I verdict**: V2C rejected all four governance v2b candidates; `flash100_allowed=false`.
- **Next card**: `6R-J Taskset/Candidate Redesign`, stop spending Flash on the current governance/research candidate families until either task diversity or domain-specific skill behavior changes.
- **6R-J status**: PASS as redesign contract. The contract blocks more Flash spend for the current governance/research discovery families and routes the next work to `governance_taskset_expansion_required` plus `research_candidate_v3_required`.
- **6R-J evidence**: `docs/reports/NEXUS_SKILL_FIT_REDESIGN_CONTRACT_2026-05-17.json`.
- **6R-M status**: PASS as cost/phase RCA. Governance V2C consumed `645906` tokens, `1667.9133` wall seconds, and `14` model calls while producing `0` effective skill rows.
- **6R-M evidence**: `docs/reports/NEXUS_SKILL_FIT_COST_PHASE_CONTRACT_GOVERNANCE_AND_TRUST_V2C_2026-05-17.json`.
- **6R-M verdict**: all observed cost concentrated in rejected candidates; cost observations remain diagnostic and cannot be merged into delivery or public cost-efficiency claims.
- **Next card**: `6R-K Research Candidate V3` and `6R-L Governance Taskset Expansion`; do not run 7R until the redesign contract produces at least one receipt-backed positive skill verdict.
- **6R-K status**: PASS as fail-closed candidate-v3 contract, not as live eligibility. The selector requires at least two observable source-discipline behavior groups among citation-chain, source-conflict, and source-validation.
- **6R-K evidence**: `docs/reports/NEXUS_RESEARCH_CANDIDATE_V3_REPORT_2026-05-17.json` and `docs/reports/NEXUS_RESEARCH_CANDIDATE_POOL_V3_2026-05-17.json`.
- **6R-K verdict**: `selected_candidate_count=0`; 45 candidates lacked observable source-discipline behavior and 4 were previous rejects. No research v3 live spend is allowed until new skills or curated metadata expose the required behaviors.
- **Next card**: `6R-L Governance Taskset Expansion`; in parallel, create or ingest source-discipline-specific research skills before retrying 6R-K live.
- **6R-L status**: PASS as taskset expansion contract, not live readiness. The selector found 30 existing governance-like tasks and selected 20, but bucket coverage is still uneven.
- **6R-L evidence**: `docs/reports/NEXUS_GOVERNANCE_TASKSET_EXPANSION_CONTRACT_2026-05-17.json`.
- **6R-L verdict**: `live_ready=false`; existing coverage is audit `2/3`, redaction `1/3`, auth `3/3`, claim-gate `14/3`, evidence-review `12/3`. Three new hidden-verifier tasks are required before governance expansion live: one audit task and two redaction tasks.
- **Next card**: `6R-L2 Governance Task Materialization`, add hidden-verifier tasks for `governance-expansion-audit-003`, `governance-expansion-redaction-002`, and `governance-expansion-redaction-003`; do not run live until the expansion contract reports `live_ready=true`.
- **6R-K2 status**: PASS as research skill supply-gap contract, not live eligibility. The contract checks current fair-pool candidates against V1/V2 rejection history and V3 observable behavior requirements.
- **6R-K2 evidence**: `docs/reports/NEXUS_RESEARCH_SKILL_SUPPLY_GAP_CONTRACT_2026-05-17.json`.
- **6R-K2 verdict**: `candidate_count=49`, `prior_reject_count=8`, `ready_candidate_count=0`, `supply_gap=true`, `research_live_allowed=false`. Do not reuse `arxiv`, `browserbase-company-research`, `browserbase-search`, `gbrain-academic-verify`, `gbrain-data-research`, or `gbrain-perplexity-research` as v2/v3 rerun candidates without source or behavior changes.
- **Next research card**: `6R-K3 Research Source-Discipline Skill Creation/Ingest`, materialize or ingest skills for citation-chain, source-conflict, and source-validation receipts; GitHub candidates may enter only external candidate pool with pinned commit, license, dependency/code/workflow scan receipts, and no runtime mount.
- **6R-L2 status**: PASS as governance task materialization. Added the missing expansion tasks to `scripts/bench/public_benchmark_commercial_expansion_v1.json` using existing hidden-verifier fixture kinds.
- **6R-L2 evidence**: `docs/reports/NEXUS_GOVERNANCE_TASKSET_EXPANSION_CONTRACT_2026-05-17.json`.
- **6R-L2 verdict**: `live_ready=true`, `proposed_new_task_count=0`, `selected_existing_task_count=15`, bucket coverage audit `4/3`, redaction `3/3`, auth `3/3`, claim-gate `10/3`, evidence-review `9/3`. Expansion taskset is ready for mutant-lane contract, but not yet live Flash spend.
- **6R-N status**: PASS as mutant-lane contract. Generated one fail-closed mutant per governance bucket.
- **6R-N evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_LANE_CONTRACT_2026-05-17.json`.
- **6R-N verdict**: `mutant_count=5`, `missing_buckets=[]`, `live_ready=true`. Governance skills cannot reach alternate/default if any mutant survives; runtime updates remain disabled.
- **Next governance card**: `6R-N2 Governance Mutant Matrix Preflight`, build a no-model/preflight matrix for the 5 mutants and verify every row carries mutant source task, expected gate `BLOCK_OR_RETURN`, evidence path, and reason-code requirements before any Flash live spend.

## 2026-05-17 Execution Update 3

- **6R-K3 status**: PASS as research source-discipline creation/ingest contract, not live eligibility.
- **6R-K3 evidence**: `docs/reports/NEXUS_RESEARCH_SOURCE_DISCIPLINE_SKILL_SPECS_2026-05-17.json`.
- **6R-K3 verdict**: `creation_spec_count=3`, `required_behavior_group_count=3`, `external_ingest_guard_present=true`, `research_live_allowed=false`. Research live remains blocked until regenerated v3 candidates expose observable citation-chain/source-conflict/source-validation receipts.
- **6R-L3 status**: PASS as lane reference gate. Governance expansion task refs are present in the selected taskset; the commercial 50 denominator is explicitly not mutated.
- **6R-L3 evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_MATRIX_PREFLIGHT_2026-05-17.json`.
- **6R-L3 verdict**: `missing_required_task_count=0`; `commercial_50_denominator_mutation_allowed=false`.
- **6R-N2 status**: PASS as governance mutant matrix preflight, not live mutant-kill evidence.
- **6R-N2 evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_MATRIX_PREFLIGHT_2026-05-17.json`.
- **6R-N2 verdict**: `row_count=5`, `missing_receipt_row_count=0`, `live_ready=true`. The matrix can be used for a bounded governance mutant live lane when quota is intentionally allocated.
- **6R-N3/6R-N4 status**: PASS as fail-closed promotion gate. The gate exists and blocks promotion until live mutant-kill evidence exists.
- **6R-N3/6R-N4 evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_PROMOTION_GATE_2026-05-17.json`.
- **6R-N3/6R-N4 verdict**: `gate_verdict=RETURN`, `promotion_allowed=false`, `flash100_allowed=false`, `missing_live_kill_evidence_count=5`.
- **6R-R1 status**: PASS as first module split. New `nexus/learning/governance_mutants.py` owns mutant matrix and mutant promotion gate contracts; `skill_fit_followup.py` keeps follow-up/candidate contracts; `skill_fit_ablation.py` remains compatibility facade.
- **6R-R2 status**: PARTIAL PASS. Added focused regression coverage for the new contracts in `tests/learning/test_skill_fit_ablation.py`; a full test-file split remains deferred to avoid expanding this task beyond the 10-file policy.
- **Verification**: `uv run pytest tests/learning/test_skill_fit_ablation.py -q` -> `54 passed`; `uv run pytest tests/benchmark/test_public_benchmark_commercial_lanes.py tests/benchmark/test_capability_tasks_schema.py -q` -> `13 passed`; `python3 -m py_compile nexus/learning/governance_mutants.py nexus/learning/skill_fit_followup.py nexus/learning/skill_fit_ablation.py scripts/ops/build_skill_fit_followup_contracts.py` -> PASS.

## Current Milestone Roadmap

### Task Card 6R-N5: Governance Mutant Live Sealing

- **Status**: PASS as local fail-closed sealing; still not skill-specific promotion evidence.
- **Scope**: Seal only the 5-row mutant matrix without touching Flash100 or commercial 50 denominator.
- **Exit condition**: every mutant row has local receipt/evidence path, `expected_gate=BLOCK_OR_RETURN`, `live_verdict=BLOCK`, and `reason_code`.
- **Fail-fast**: any survived mutant, missing evidence path, selected-only contribution, or hidden verifier disabled.
- **Do not**: use normal delivery PASS as mutant kill evidence.
- **Evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_LIVE_SEALING_2026-05-17.json` reports `sealed_row_count=5`, `failed_row_count=0`, and `candidate_bound_kill_evidence_count=0`.
- **Residual gate**: Candidate-bound mutant kill evidence is still required before governance skill promotion.

### Task Card 6R-K4: Research External Ingest Guard Implementation

- **Status**: PASS as no-network ingest guard; implementation remains candidate-pool only.
- **Scope**: Define source URL/commit/license/security receipt requirements for research skills without fetching external sources.
- **Exit condition**: external candidates can be written only to candidate pool with pinned commit, license decision, dependency/static/workflow scan receipt, and at least two observable source-discipline behavior groups.
- **Fail-fast**: unpinned source, runtime mount attempt, unknown license, or missing security receipt.
- **Do not**: auto-promote GitHub/external skills to runtime.
- **Evidence**: `docs/reports/NEXUS_RESEARCH_EXTERNAL_INGEST_GUARD_2026-05-17.json` reports `required_field_count=7`, `required_check_count=6`, `runtime_mount_allowed=false`, and `network_fetch_performed=false`.

### Task Card 6R-R3: Full Ablation Module Split

- **Status**: PASS for first full facade/core split.
- **Scope**: Moved the ablation implementation into `skill_fit_ablation_core.py` while keeping `skill_fit_ablation.py` as a compatibility facade.
- **Exit condition**: existing CLI imports keep working; focused tests and CLI help still pass.
- **Fail-fast**: public imports break, duplicate behavior diverges, or tests require fixture rewrites.
- **Evidence**: `nexus/learning/skill_fit_ablation.py` is now 51 lines; `nexus/learning/skill_fit_ablation_core.py` holds the preserved core implementation.

### Task Card 7R: Flash100 Route-Cost Regression

- **Status**: BLOCKED.
- **Unlock condition**: at least one receipt-backed `(capability, skill_id)` reaches alternate/default and the candidate-bound mutant/research gates no longer report `promotion_allowed=false`.

### Task Card 8R: Pro18 Sanity

- **Status**: BLOCKED.
- **Unlock condition**: 7R passes with clean delivery/trust/cost evidence.

### Task Card 9R: GPT-5.5 Paired Baseline

- **Status**: BLOCKED.
- **Unlock condition**: Flash/Pro gates are clean, fixed public taskset and verifier are frozen, and public disclosure/evidence bundle is replayable.

## 2026-05-17 Execution Update 4

- **6R-N5 status**: PASS as local governance mutant live sealing. The report seals 5/5 mutant rows with fail-closed BLOCK/RETURN-style receipts, but does not bind those kills to a candidate skill.
- **6R-N5 evidence**: `docs/reports/NEXUS_GOVERNANCE_MUTANT_LIVE_SEALING_2026-05-17.json`.
- **6R-N5 verdict**: `sealed_row_count=5`, `failed_row_count=0`, `candidate_bound_kill_evidence_count=0`, `promotion_allowed=false`.
- **6R-K4 status**: PASS as external ingest guard. The report defines the required candidate metadata and scan receipts without performing network fetches or runtime mounts.
- **6R-K4 evidence**: `docs/reports/NEXUS_RESEARCH_EXTERNAL_INGEST_GUARD_2026-05-17.json`.
- **6R-K4 verdict**: `required_field_count=7`, `required_check_count=6`, `runtime_mount_allowed=false`, `network_fetch_performed=false`.
- **6R-R3 status**: PASS as facade/core Module split. `skill_fit_ablation.py` is now a compatibility facade; the preserved implementation lives in `skill_fit_ablation_core.py`.
- **6R-R3 evidence**: `uv run python scripts/ops/build_skill_fit_ablation_plan.py --help` PASS; `uv run python scripts/ops/run_skill_fit_ablation_matrix.py --help` PASS.
- **Verification**: `uv run pytest tests/learning/test_skill_fit_ablation.py -q` -> `55 passed`; `uv run pytest tests/benchmark/test_public_benchmark_commercial_lanes.py tests/benchmark/test_capability_tasks_schema.py -q` -> `13 passed`; `python3 -m py_compile nexus/learning/skill_fit_ablation.py nexus/learning/skill_fit_ablation_core.py nexus/learning/governance_mutants.py nexus/learning/skill_fit_followup.py scripts/ops/build_skill_fit_followup_contracts.py` -> PASS.

## Next Milestone Task Cards

### Task Card 6R-N6: Candidate-Bound Mutant Kill Evidence

- **Status**: PASS as bounded 10-row live.
- **Scope**: Bound mutant rows to two governance candidate skill arms and rerun only that bounded matrix.
- **Exit condition**: every candidate-bound mutant row has `(capability, skill_id, mutant_id)`, live verdict, receipt path, evidence path, and trust mismatch 0.
- **Fail-fast**: any survived mutant, selected-only evidence, or normal delivery PASS substituted for mutant kill.
- **Evidence**: `/private/tmp/nexus_governance_candidate_bound_mutant_live_20260517/live_summary.json` reports `completed_rows=10`, `pass_count=10`, `return_count=0`; `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_BOUND_MUTANT_CATALOG_2026-05-17.json` reports `alternate_count=2`.

### Task Card 6R-K5: External Research Candidate Pool Writer

- **Status**: PASS as metadata-only candidate-pool writer.
- **Scope**: Take guard-passing external source metadata and write candidate-pool entries only.
- **Exit condition**: generated candidates include pinned source, license/security/workflow receipts, and at least two source-discipline behavior groups.
- **Fail-fast**: runtime mount attempt, unknown license, missing commit SHA, or missing security receipt.
- **Evidence**: `docs/reports/NEXUS_RESEARCH_EXTERNAL_CANDIDATE_POOL_2026-05-17.json` reports `candidate_count=3`; `docs/reports/NEXUS_RESEARCH_CANDIDATE_V3_EXTERNAL_REPORT_2026-05-17.json` reports `selected_candidate_count=3`.

### Task Card 6R-R4: Focused Test-File Split

- **Scope**: Split `tests/learning/test_skill_fit_ablation.py` into core/follow-up/promotion/mutant focused files.
- **Exit condition**: old compatibility import smoke remains; focused files pass without changing behavior.
- **Fail-fast**: coverage drops or fixtures fork.

## 2026-05-17 Execution Update 5

- **6R-N6 status**: PASS. Candidate-bound governance mutant live completed `10/10` rows.
- **6R-N6 evidence**: `/private/tmp/nexus_governance_candidate_bound_mutant_live_20260517/live_summary.json` and `docs/reports/NEXUS_GOVERNANCE_CANDIDATE_BOUND_MUTANT_CATALOG_2026-05-17.json`.
- **6R-N6 verdict**: `cso` and `acceptance-evidence-failclosed` reached mutant-suitability `alternate` with `kill_rate=1.0`.
- **6R-K5 status**: PASS. External research candidate pool writer generated 3 metadata-only candidates and v3 selected all 3.
- **6R-K5 evidence**: `docs/reports/NEXUS_RESEARCH_EXTERNAL_CANDIDATE_POOL_2026-05-17.json`, `docs/reports/NEXUS_RESEARCH_CANDIDATE_V3_EXTERNAL_REPORT_2026-05-17.json`, and `docs/reports/NEXUS_RESEARCH_CANDIDATE_POOL_V3_EXTERNAL_2026-05-17.json`.
- **6R completion status**: PASS for entering 7R route-cost regression only.
- **6R completion evidence**: `docs/reports/NEXUS_6R_COMPLETION_READINESS_2026-05-17.json`.
- **7R boundary**: `route_cost_7r_allowed=true`, but `public_claim_allowed=false`, `pro18_allowed=false`, and `gpt55_paired_baseline_allowed=false`.

## 7R Entry Task Cards

### Task Card 7R-A: Flash100 Route-Cost Regression Preflight

- **Status**: PASS.
- **Scope**: Build/verify a Flash100 route-cost matrix using fixed commercial denominator and no public claim.
- **Exit condition**: taskset hash stable, hidden verifier enabled, skill receipt requirements present, cost ledger fields present.
- **Fail-fast**: denominator drift, missing token/wall/model-call ledger, or public claim attempt.
- **Evidence**: `docs/reports/NEXUS_7R_FLASH100_TASKSET_CONTRACT_2026-05-17.json` reports `selected_task_count=100`; `docs/reports/NEXUS_7R_ROUTE_COST_PREFLIGHT_2026-05-17.json` reports `tasks_checked=100`, `failure_count=0`, and `route_cost_7r_live_allowed=true`.

### Task Card 7R-B: Flash100 Route-Cost Live

- **Status**: READY.
- **Scope**: Run Flash100 only after 7R-A preflight passes.
- **Exit condition**: verified delivery does not regress, trust mismatch remains 0, cost telemetry conserved.
- **Fail-fast**: first delivery fail, trust mismatch, missing receipt, or suspicious zero-fill.

### Task Card 7R-C: Route-Cost Claim Separation

- **Scope**: Generate observation-only report that separates delivery, cost, and skill-fit claims.
- **Exit condition**: cost claim may be PASS/NEUTRAL/REGRESSED independently; delivery claim cannot borrow cost result.
- **Fail-fast**: any public wording that treats diagnostic 7R as final promotion.

## 2026-05-17 Execution Update 6

- **7R-A status**: PASS as preflight only.
- **7R-A evidence**: `docs/reports/NEXUS_7R_FLASH100_TASKSET_CONTRACT_2026-05-17.json` and `docs/reports/NEXUS_7R_ROUTE_COST_PREFLIGHT_2026-05-17.json`.
- **7R-A verdict**: public benchmark manifests provide 111 available tasks; Flash100 taskset froze 100 selected tasks with `taskset_hash=5085843b569850e3ca398ca99b0ee71a523c263f5570b3c74933a3c03d426e72`; route-cost preflight checked 100 tasks with `failure_count=0`.
- **7R-B status**: READY but not started. It is the first Flash100 live long-run and remains diagnostic, not public claim evidence.
