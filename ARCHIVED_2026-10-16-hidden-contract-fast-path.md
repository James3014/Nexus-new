# ARCHIVED 2026-10-16 (hidden-contract fast path)

Physical deletion of the benchmark-keyed local fixers that let a run "with a model" deliver a
hard-coded benchmark answer without any model output. Tracking issue: #2339. Decision: Owner
(James), in chat on 2026-10-16: delete physically ("1 跟 2 都刪"), not the
unreachable-plus-manifest variant of `ARCHIVED_2026-10-12.md` / `ARCHIVED_2026-10-13*.md`. The
physical-deletion precedent is #2197 (Owner decision on #1927).

Originals are preserved on branch `archive/2026-10-16-hidden-contract-fast-path`, cut at
`219fa4ca7dce887626ea19a7919f4a8f409a9a6a`. That commit is the base the change was written on and
an ancestor of the base #2347 merged onto (`62ee368d3`). The only commit in between that touched these
files (`9d919f67f`, #2325, strict-lane gate inputs in `sprint_service.py`) did not touch any of the removed
code, so the archive holds the removed code exactly as it was deleted.

## Evidence

The 2026-10-16 zero-model proof (`~/Workspace/nexus-handoffs/2026-10-13-online-ab/CAPABILITY_STATUS_20261016.md`,
run D1, `proofs_20261016/p16_nonstrict_D1/with_nexus_1792107603.jsonl`) ran the P16 set
(`scripts/bench/public_benchmark_nexus_value_v1.json`) in the non-strict lane with a NOOP model:
12/12 hidden-verified SUCCESS. The winner sources were:

| P16 task | winner source | model calls |
| --- | --- | --- |
| hidden-001, context-001 | `local_hidden_contract_fast_path` (baseline local-first patch) | 0 |
| repair-001, repair-002 | `local_hidden_contract_fast_path` (sprint fast path) | 0 |
| gov-001, evidence-002 | `local_preflight` | 0 |
| gov-002, evidence-001, trust-001, trust-002 | `local` (local mutator after the model failed) | 1 |
| hidden-002, context-002 | `local(llm_error_..._fallback_local)` (baseline fallback) | 1 |

The strict and treatment lanes already switched these paths off (`NEXUS_DISABLE_*` env from
`scripts/bench/capability_ab_runner.py` / `treatment_lane.py`) and refused local delivery
(`model_required_final_delivery`); their A2/A3/D2 runs show `nexus_llm_baseline_failed` and
`model_required_no_model_candidate` on the same tasks.

## Removed

| Where | What | Lines |
| --- | --- | --- |
| `nexus/research/sprint_service.py` | `_has_hidden_contract_fast_path` (matched `def merge_limits`, `def remaining_ms`, `def rlm_harder_v2_repair_budget`) | 10 |
| `nexus/research/sprint_service.py` | `_should_try_local_preflight_before_llm` (matched `build_response`, `def redact`, `phase_ready`, 7 `rlm_harder_v2_*` names, ...) | 30 |
| `nexus/research/sprint_service.py` | per-candidate branches: hidden-contract fast path (`local_hidden_contract_fast_path`), local preflight (`local_preflight`), post-model hidden invariant swap and hidden invariant shadow candidate (`local_hidden_shadow`), the shadow early `break`, and their env switches | about 160 |
| `nexus/app/research_flow_service.py` | `_build_hidden_contract_local_first_patch` and its call in `_build_baseline_patch` (`hidden_contract_local_first_before_llm`) | 45 |
| `nexus/app/research_flow_service.py` | baseline fallback to the local mutator after a model failure (`fallback_local_due_to_llm_failure`, `local(..._fallback_local)` labels) | 30 |
| `nexus/research/flow/route_decider.py` | `benchmark_hidden_contract_fast_path` route (matched "verification test" / "renamed public field" + "canonical field"), its risk cap and route feature | 23 |
| `nexus/research/flow/evidence_packer.py` | research-role override for that route feature | 2 |

Totals for product code: 4 files, about 311 lines removed, 31 added.

## Behaviour after the change

- A sprint with a model generator configured delivers only a model-owned candidate
  (`llm*`, `model*`, `nexus_llm*`). Otherwise it returns FAILED with
  `model_required_model_delivery_failed` and winner `model_required_no_model_candidate`; this is
  the strict lane's existing gate, now applied whenever a model runs. Local candidates may still be
  scored as support (DDTree pool, guard fallback, emergency valve) but are never delivered.
- A failed model baseline returns `nexus_llm_baseline_failed` in every lane (`baseline_source_policy`
  `llm_no_local_fallback` when the model was not required).
- Pure local mode (no model configured, `llm_mode=False` or the learn-SLO guard) is unchanged.
- Strict and treatment lanes: unchanged.

## Kept on purpose (follow-ups)

- `nexus/research/local_sprint_mutator.py` (the answer table behind `generate_local_candidate` and
  `generate_local_companion_edits`) stays: pure local mode, nightshift, the bench file-task runner
  and many tests still use it. Retiring it is a separate batch.
- `scripts/bench/*` classifiers that recognise `local_hidden_contract_fast_path` / `local_preflight`
  in historical rows (`benchmark_eligibility.py`, `cost_evidence_classifier.py`,
  `route_cost_optimizer.py`, `teacher_student_gap_matrix.py`) stay, so old artifacts keep being
  labelled as non-model solves.
- The `NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH` / `NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM` /
  `NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW` exports in the bench runners are now no-ops; they stay
  because bench tests pin them.

## Tests

No test function was deleted or renamed (the exact-base impact gate reads a missing base test id as
lost coverage). The 24 tests that asserted the removed behaviour keep their ids and now assert its
absence; each fails on the base commit. New: `tests/research/test_no_benchmark_local_fast_path.py`
runs every P16 fixture with a NOOP model in the non-strict lane (24 cases, all failing on base).

## Follow-up: answer-table reachability (PR-5c-2)

#2347 left three ways the local answer table could still reach a model run's delivery. This
follow-up closes them:

- **Self-heal support block.** With `NEXUS_MODEL_REQUIRED_EXECUTION_MODE=model_participation_only`
  outside the symmetric lane, the self-heal prompt carried the local mutator's solution as
  `[NEXUS LOCAL SUPPORT CANDIDATE]`. An echoing model returned it as `llm_self_heal`. The block is
  removed. A self-heal after a model call that produced no candidate restarts from the original source,
  never from the local fallback.
- **Companion edits.** The baseline flow wrote fixture-keyed companion files (`invoice.py`/`tax.py`
  pricing, nightshift `runner.py`/`store.py`) next to a model patch and kept them on success. The
  sprint's in-place scorer applied them while scoring model candidates. Now companions only accompany
  a local-mode patch, and a model candidate is scored exactly as it is delivered.
- **Skipped model baseline / learn-SLO guard.** With `llm_mode` on and the model baseline skipped
  (route-cost `skip_llm_baseline`), the baseline flow delivered the local answer table. A NOOP probe
  solved 4/12 P16 tasks this way. A sprint whose model the learn-SLO guard withheld also delivered
  locally. A model-configured run now returns `model_baseline_skipped` and escalates to the model
  sprint, and the sprint's model-only delivery gate also covers `config.llm_mode`.

