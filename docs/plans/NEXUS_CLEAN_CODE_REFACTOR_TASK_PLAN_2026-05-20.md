# Nexus Clean Code Refactor Task Plan

Status: `PLAN_ONLY`
Date: `2026-05-20`
Source audit: `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_CLEAN_CODE_AUDIT_REPORT.md`
Baseline commit: `17c1409d`
Baseline CI: `uv run scripts/ops/ci_gate.py` PASS on `17c1409d` before this plan was written.

## 1. Scope

This plan turns the Clean Code / Linus audit into bounded Nexus task cards.

The plan does not authorize runtime behavior changes, public benchmark claims, Swarm/NSP work, or broad path cleanup. Each implementation slice must stay within the local `AGENTS.md` constraints:

- max touched files per slice: `10`;
- allowed paths: project root, `scripts/ops/`, `nexus_wiki_vault/`, `docs/`;
- forbidden paths: `.obsidian/`, `benchmarks/`, `logs/`, `nexus_swarm/`, `packages/`;
- every failure becomes a lesson in the learning closure matrix, ADR, or this plan.

## 2. Current Baseline

Local verification on `2026-05-20`:

| Module | Current line count | Audit concern |
| --- | ---: | --- |
| `nexus/app/research_flow_service.py` | 4046 | orchestration, route decision, evidence packing, RLM, skill/runtime receipts, and security helpers are coupled in one file |
| `nexus/engine/pipeline_repair.py` | 932 | repair driver, audit evaluation, recursive repair, and escalation are still in one class/module |
| `nexus/engine/capability_planner.py` | 1472 | capability metadata, route planning, learning policy, and cost/policy overlays are coupled |
| `nexus/engine/learning_policy_loader.py` | 733 | policy loading is coupled to concrete JSON/JSONL paths and runtime merge details |

Hot seams confirmed locally:

- `research_flow_service.py`: `_classify_commercial_signal`, `_write_msa_receipt_reports`, `_build_research_context`, `_collect_route_signals`, `_decide_flow`;
- `pipeline_repair.py`: `_evaluate_audit_result`, `_handle_escalation`, `_perform_escalation`;
- `capability_planner.py`: `_apply_learning_policy`;
- root contains many legacy scripts/reports that need retention classification before cleanup.

## 3. Clean Code / Linus Guardrails

All slices must follow these rules:

1. Prefer deep modules over shallow pass-through extraction.
2. Do not create a new seam unless it gives locality or has at least a planned second adapter.
3. Move data contracts first, behavior second, deletion last.
4. Preserve fail-closed gates: no extracted module may update runtime policy or unlock public benchmark by default.
5. Use guard clauses for high-risk decision logic before extracting it.
6. Keep each slice independently testable and revertible.

## 4. Task Cards

### CC-PREFLIGHT: Baseline Freeze and Plan Crosswalk

Goal: freeze the current post-routing-refactor baseline and prove the Clean Code plan does not duplicate or bypass already-completed optimization contracts.

Scope:

- compare this plan with:
  - `docs/plans/NEXUS_OPTIMIZATION_CONTRACT_AND_RETENTION_2026-05-19.md`;
  - `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`;
  - `nexus_routing_spec_v2.md` status as reflected in local backlog gates;
- record `already_done`, `next`, `excluded`, and `blocked` status;
- commit the plan as a clean baseline before implementation.

Exit:

- baseline commit is recorded;
- full CI baseline is recorded;
- crosswalk table exists in this plan;
- no runtime, benchmark, Swarm/NSP, or root-file move happens in this preflight.

Verification:

- `git status --short --untracked-files=all`;
- `git rev-parse --short HEAD`;
- markdown review only; no runtime test required for this plan-only commit.

### CC-0: Root Hygiene Retention Inventory

Goal: classify root-level legacy scripts/reports before moving anything.

Scope:

- inspect root files only;
- produce a retention manifest under `docs/reports/` or `docs/plans/`;
- no deletion and no move.

Exit:

- every root-level script/report candidate has one of: `keep_tracked_source`, `archive_candidate`, `ops_script_candidate`, `test_candidate`, `unknown_hold`;
- no tracked file is moved;
- worktree remains clean except the manifest.

Verification:

- `git status --short --untracked-files=all`;
- focused test not required unless script logic is added.

### CC-1: Research Flow Route Decision Module

Goal: extract route decision and signal collection from `research_flow_service.py` behind a small interface.

Proposed module:

- `nexus/research/flow/route_decider.py`

Move candidates:

- `_classify_commercial_signal`;
- `_collect_route_signals`;
- `_decide_flow`;
- related pure route feature helpers only.

Exit:

- `research_flow_service.py` delegates route choice to `route_decider`;
- behavior-equivalent focused tests pass;
- no evidence packing or runtime receipt logic moves in this slice.

Verification:

- existing route / research flow focused tests;
- `uv run pytest tests/app/test_research_flow_service.py -q` when feasible.

### CC-2: Research Flow Evidence Packer

Goal: isolate report and evidence packaging from orchestration.

Proposed module:

- `nexus/research/flow/evidence_packer.py`

Move candidates:

- `_write_msa_receipt_reports`;
- `_build_research_context`;
- receipt/report shaping helpers that do not decide route or execute repair.

Exit:

- evidence/report packing can be tested without running full flow;
- claim/public gate fields remain read-only;
- report paths and schema output are unchanged.

Verification:

- focused evidence/report tests;
- selected `test_research_flow_service` cases that assert receipt/report output.

### CC-3: Pipeline Repair Audit Evaluator

Goal: split audit verdict evaluation from repair loop execution.

Proposed module:

- `nexus/engine/repair/audit_evaluator.py`

Move candidates:

- `_evaluate_audit_result`;
- hallucination/audit bundle shaping tied to audit verdicts.

Exit:

- `PipelineRepair` drives the loop, `audit_evaluator` computes verdict readouts;
- nested audit logic is converted to guard clauses where safe;
- audit fail-closed semantics unchanged.

Verification:

- `uv run pytest tests/engine/test_pipeline_repair.py -q`;
- any existing hallucination/audit evaluator tests discovered by `rg`.

### CC-4: Pipeline Repair Escalation Manager

Goal: split escalation routing from the repair/audit loop.

Proposed module:

- `nexus/engine/repair/escalation_manager.py`

Move candidates:

- `_handle_escalation`;
- `_perform_escalation`;
- escalation payload shaping.

Exit:

- escalation can be tested as a separate module with explicit inputs;
- `PipelineRepair` retains only core repair/audit loop flow;
- no Swarm/NSP sidecar behavior is added.

Verification:

- pipeline repair focused tests;
- any escalation-specific tests discovered by `rg`.

### CC-5: Capability Planner Policy Applier

Goal: decouple dynamic learning policy application from capability planning.

Proposed module:

- `nexus/engine/planner/policy_applier.py`

Move candidates:

- `_apply_learning_policy`;
- promoted/penalized capability normalization;
- policy conflict resolution.

Exit:

- `CapabilityPlanner` remains the planning facade;
- policy applier has deterministic input/output tests;
- runtime update/public benchmark flags remain forbidden unless an apply gate passes.

Verification:

- `uv run pytest tests/engine/test_capability_planner.py -q`;
- focused policy loader tests.

### CC-6: Capability Planner A/B Evaluator

Goal: isolate A/B or route-cost weighting logic from capability metadata and base planning.

Proposed module:

- `nexus/engine/planner/ab_evaluator.py`

Exit:

- scoring/weighting can be tested without constructing the full planner;
- planner output remains schema-compatible;
- no public benchmark claim is inferred from internal A/B metrics.

Verification:

- capability planner tests;
- route/cost focused tests if touched.

### CC-7: Learning Policy Store Interface

Goal: decouple `learning_policy_loader.py` from concrete JSON/JSONL persistence paths.

Proposed module:

- `nexus/engine/learning_policy_store.py`

Exit:

- a `LearningPolicyStore` interface reads policy payloads;
- default adapter preserves current JSON/JSONL behavior;
- future LanceDB/vector adapters can be added without editing planner logic.

Verification:

- focused tests for runtime learning policy merge;
- planner integration test proves same selected capabilities as baseline.

### CC-8: Root Script Cleanup Plan

Goal: after CC-0 inventory, move only safe ops scripts into `scripts/ops/` and test-like files into `tests/`.

Scope:

- only files classified as safe in CC-0;
- no deletion;
- no generated evidence/report moves without a retention manifest.

Exit:

- moved scripts have equivalent invocation docs or wrapper compatibility;
- imports/path assumptions are fixed;
- old root clutter is reduced without losing tracked provenance.

Verification:

- `uv run scripts/ops/ci_gate.py`;
- targeted smoke for every moved executable script.

## 5. Recommended Execution Order

1. `CC-PREFLIGHT`: freeze baseline and crosswalk with previous refactor plans.
2. `CC-0`: inventory first, because cleanup without classification risks deleting evidence.
3. `CC-1`: route decision extraction, because it reduces `research_flow_service.py` change pressure without touching evidence.
4. `CC-2`: evidence packer extraction, after route behavior is stable.
5. `CC-3`: audit evaluator extraction.
6. `CC-4`: escalation manager extraction.
7. `CC-5`: policy applier extraction.
8. `CC-6`: A/B evaluator extraction.
9. `CC-7`: learning policy store interface.
10. `CC-8`: root script cleanup only after inventory and tests.

## 6. Milestone Roadmap

| Milestone | Done when |
| --- | --- |
| `CC-MP Preflight Frozen` | baseline commit, CI status, and plan crosswalk are committed |
| `CC-M0 Hygiene Ready` | root files classified, no moves performed |
| `CC-M1 ResearchFlow split` | route decision and evidence packing are behind separate modules and focused tests pass |
| `CC-M2 Repair split` | audit evaluator and escalation manager are isolated from the repair driver |
| `CC-M3 Planner split` | policy applier and A/B evaluator are isolated from planning facade |
| `CC-M4 Policy store seam` | learning policy persistence is behind a store interface |
| `CC-M5 Workspace cleanup` | root clutter reduction is tested and reversible |

## 7. Stop Conditions

Stop and re-plan if:

- a slice would exceed 10 touched files;
- a slice needs forbidden paths;
- a refactor changes runtime dispatch semantics;
- a public benchmark or runtime apply claim appears in an internal-only artifact;
- tests require broad benchmark execution before a focused seam test exists.

## 8. Next Action

Start with `CC-0 Root Hygiene Retention Inventory`.

The first implementation should add a manifest/report only. It should not move or delete root files.

## 9. Preflight Crosswalk

This crosswalk prevents the Clean Code refactor from re-opening already-closed routing/optimization contracts.

| Area | Prior status | Clean Code action |
| --- | --- | --- |
| ContextHub / context budget | `M1` has audited context assembly and runtime adapter contracts | Do not rework in CC slices unless a target module directly calls ContextHub; keep as dependency |
| Skeleton-first CodeIntel | `M2` implemented as bounded exact-symbol/rationale adapter | Do not duplicate; CC tasks may consume existing adapter only |
| Hybrid retrieval | `M3` implemented with retrieval receipt and BM25/dense fusion contract | Do not move retrieval logic during ResearchFlow split |
| Route DAG / runtime dispatcher | `M5` implemented with pregate, runtime plan, forced-swarm serialization, and required-rescue guard | CC-1 may reorganize route decision helpers, but must not change route DAG semantics |
| Claim/evidence read model | `M6` implemented with CompletionEnvelope, mutation assurance, sealed evidence, and hash-valid blockers | CC-2 may pack evidence, but must preserve read-model contract fields |
| Skill-fit replacement | `M7` implemented with cleanliness gate and apply plan | CC tasks must not change runtime default skill policy |
| Workspace hygiene | `M8` implemented as retention dry-run and per-run report output routing | CC-0 extends this with root file classification only; no moves/deletes |
| RLM routing spec v2 | Implemented as bounded X/R-loop orchestration receipts; full recursive dispatch requires separate authorization | CC-1/CC-2 must preserve `rlm_bounded_orchestration_receipt` and not enable recursive dispatch |
| Swarm / NSP / Go sidecar | Explicitly excluded / forbidden-path boundary | Do not touch in this Clean Code plan |
| Public benchmark | Separate gate; not unlocked by internal refactor or plan-only docs | Do not claim public readiness from CC tasks |

## 10. Baseline Freeze Record

| Field | Value |
| --- | --- |
| Baseline commit | `17c1409d` |
| Baseline branch | `main` |
| Baseline full gate | `uv run scripts/ops/ci_gate.py` PASS before this plan |
| Current preflight artifact | `docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md` |
| Claim class | `PLAN_ONLY` |
| Runtime update allowed | `false` |
| Public benchmark allowed | `false` |
