# TRAJECTORY_CORPUS_READINESS_REPORT

Experiment: NEXUS_SYSTEM_ONE_CLM_V2 / TRACK_1_TRAJECTORY_VERIFIER_HEAD
Audit date: 2026-09-29
Decision: **TRAJECTORY_CORPUS_NOT_READY**
Claim ceiling: EXPERIMENTAL_SHADOW_ONLY

## T0_CURRENT_STATE_AUDIT

- Canonical collaboration source: GitHub `James3014/Nexus-new/main`.
- Current verified upstream main SHA: `57edae9832392e3e369ee039b2e12f18b8c433df`.
- Current operating mode: `BOOTSTRAP`; bounded new work defaults to DIRECT_CANONICAL, `auto_chain: false`.
- First Mac checkout `/Users/james/workspace/Nexus-new`: branch `feat/provider-adoption-experiment-v1`, HEAD `63b67975f9b0c0032d83e91d5fc58ecb5bb55be7`, dirty.
- Its local `origin/main` was `2799001883f1abe8cbd7dee8c25e71b0b5436401`, behind verified upstream main.
- Second Mac checkout `/Users/jameschen/Workspace/Nexus-new`: branch `codex/issue-1144-remote-tool-identity`, HEAD `22eb30206d187975e4d67cd70f89c4634df41902`, dirty.
- The two machines are treated as separate evidence domains; no cross-host corpus mixing was performed.
- Active Nexus gateway root: `/Users/james/Library/Application Support/Nexus/gateway-direct/deployments/r1-de6bb162d89e8b22d491113afa8405aae1c75ca0`.
- Gateway reports deployed source head `a316448de6b056a9ba1be910ac5f97a49afe2452`, observed upstream main `57edae...`, `upstream_freshness=STALE`.
## Candidate Evidence Collector

- Current main collector schema: `nexus.clm_candidate_evidence.v1`.
- Collection result schema: `nexus.clm_candidate_evidence_collection.v1`.
- Group manifest schema: `nexus.clm_candidate_evidence_group_manifest.v1`.
- Current main preserves winner, losers, payload hashes/refs, verifier evidence, label quality, source revision, immutable comparison group, and `dataset_eligible`.
- Current main wiring includes delegated retry isolated-verifier evidence, BattleSwarm mechanical-gate evidence, local committee selected-candidate isolated evidence, generic committee `CRITIC_AGGREGATE`, and S2T `TRACE_ONLY`.
- Active runtime live store contains exactly 1 complete group, 2 rows, 1 task, and 0 dataset-eligible rows.
- Both live rows are `CRITIC_AGGREGATE`; one says PASS and one FAIL, but neither is admissible as strong PASS/FAIL truth.
- Live group manifest `eligible_count=0`.

## Existing trajectory-related fields

Present in candidate rows:
- `task_id`, `attempt_id`, `candidate_id`, `source_revision`
- candidate payload/hash/ref
- verifier status, label quality, verifier evidence/ref
- selected/winner identity, comparison-group identity

Missing for a trainable trajectory representation:
- `trajectory_id`
- `step_index`
- pre-action state/context snapshot
- exact action
- action type
- action result
- causal/temporal ordering boundary
- per-step timestamp or equivalent monotonic order
## Receipt / trace audit

- Canonical runtime receipts contain planner/runtime stage summaries, not an agent's ordered exact `state -> action -> result` sequence.
- Fields named `state` are largely capability-plan states such as required/optional/conditional.
- The observed `action: candidate` is a planner/local-assist signal, not the exact next agent action.
- LocalHeal receipts provide final verifier-oriented evidence but do not provide a leakage-safe ordered step sequence.
- Therefore reconstructing earlier state from these receipts would require inference and risks future-evidence leakage.
- No existing receipt was admitted as a synthetic trajectory row.

## Corpus counts at T1

- Strong-label candidate groups usable for trajectory training: **0**.
- Strong-label trajectories: **0**.
- PASS trajectories: **0**.
- FAIL trajectories: **0**.
- UNKNOWN trajectories: current weak/trace evidence exists, but it is not a trainable strong-label corpus.
- Task families with leakage-safe PASS/FAIL trajectory coverage: **0**.
- Task-disjoint train/dev split capability: **NO**.
- Family-disjoint train/dev split capability: **NO**.

## Leakage / duplication audit

- FINAL_HOLDOUT_DO_NOT_TRAIN was frozen separately with hashes for R01-R10, Candidate A/B evidence, historical oracle/fix identities, ranking blind v2, and the 30 decision cases.
- R01-R10 must not be paraphrased, rewritten, or recreated as near-duplicate training fixtures.
- Current receipts do not prove which information was visible before each action; using final verifier output inside reconstructed earlier state would create future leakage.
- Selected winner, critic aggregate, trace-only, self-report, and model confidence remain non-authoritative labels.
## T1 Gate

**TRAJECTORY_CORPUS_NOT_READY**

This is not an N-threshold failure. It is a representation/provenance failure:
1. zero strong-label live rows;
2. no leakage-safe ordered state/action steps;
3. no task-disjoint PASS/FAIL trajectory corpus.

Fine-tuning is therefore forbidden in this session under the stated stop conditions.

## Minimum passive instrumentation proposal

Do not create a second candidate collector. Add an append-only trajectory sidecar under the existing CLM research evidence root.

Proposed step schema: `nexus.clm_trajectory_step.v1`.
Each step records only information available at action time:
`task_id, trajectory_id, attempt_id, candidate_id, step_index, source_revision, state_ref/state_sha256, action_type, action_payload/action_sha256, action_result_ref/action_result_sha256, observed_at, parent_step_sha256`.

The state snapshot must be sealed before action execution. The action result may be appended/bound after execution, but final candidate verifier outcome must NOT be embedded into earlier state.

Final outcome should be a separate immutable trajectory-to-candidate-evidence binding that references an existing strong-label candidate row (`ISOLATED_VERIFIER` or `MECHANICAL_GATE`) only after the trajectory completes.

Instrumentation remains passive:
- no routing effect
- no winner-selection effect
- no acceptance effect
- no verifier replacement
- no production behavior change
- collection failure is telemetry-only

Next Gate: accumulate real multi-task, multi-family PASS/FAIL trajectories with strong verifier labels, then rerun T1 readiness. T2/T3/T4 remain blocked.
