# Nexus Refactor Clean Baseline Plan - 2026-05-20

## Status

- workspace_cleanup_status: READY_FOR_BASELINE_CHECKPOINT
- sf_current_overlay_status: PASS
- required_skill_manifest_status: PASS
- runtime_report_noise_restored: true
- destructive_delete_allowed: false

## Preserved Evidence

- Current SF state report:
  - `docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md`
- Current runtime skill overlay:
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json`
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.md`
- Current overlay smoke:
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json`
- Original skill map:
  - `docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json`
  - `docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.md`
- Required skill manifest:
  - `docs/reports/NEXUS_SF_REFACTOR_REQUIRED_SKILL_MANIFEST_2026-05-20.json`
- V32 SF closure bundle:
  - `docs/reports/NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_LIVE_ROLLUP_V32_2026-05-19.json`
  - `docs/reports/NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_LIVE_ROLLUP_V32_2026-05-19.md`
  - `docs/reports/NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_SKILL_FIT_CATALOG_V32_2026-05-19.json`
  - `docs/reports/NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.json`
  - `docs/reports/NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.md`

## Archived Evidence

- `docs/reports/archive/sf-retention-current-2026-05-20/`
- Moved superseded SF report artifacts: 134
- Archive result:
  - `docs/reports/NEXUS_SF_WORKSPACE_RETENTION_APPLY_RESULT_CURRENT_2026-05-20.json`
  - `docs/reports/NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json`

## Baseline File Groups

### Group 1: Runtime and Harness Code

- `nexus/app/research_flow_service.py`
- `nexus/engine/capability_planner.py`
- `scripts/bench/capability_ab_runner.py`
- `tests/app/test_research_flow_service.py`
- `tests/benchmark/test_capability_ab_runner.py`
- `tests/engine/test_capability_planner.py`

### Group 2: SF Learning and Discovery Modules

- `nexus/learning/`
- `nexus/research/candidate_pool_policy.py`
- `scripts/ops/build_sf_*`
- `scripts/ops/evaluate_*skill*`
- `scripts/ops/optimize_sf_primary_skill_descriptions.py`
- `tests/learning/`
- `tests/ops/test_build_sf_*`
- `tests/ops/test_evaluate_*skill*`
- `tests/ops/test_optimize_sf_primary_skill_descriptions.py`

### Group 3: Skill Assets

- Keep every directory listed in:
  - `docs/reports/NEXUS_SF_REFACTOR_REQUIRED_SKILL_MANIFEST_2026-05-20.json`
- Do not delete or move required skill assets before the large refactor.
- Generated challenger skill IDs may be non-human-readable; original names are recorded in:
  - `docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.md`

### Group 4: Documentation and Lessons

- `docs/plans/CONTEXT_ENGINEERING_SYNC.md`
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- current SF report bundle under `docs/reports/`

## Excluded From Baseline

The following tracked runtime/tool state was restored before this baseline plan:

- `.nexus/reports/acceptance_check.md`
- `.nexus/reports/learn/phase_slo_summary.json`
- `.nexus/reports/learn/phase_writeback.jsonl`
- `.serena/project.yml`

Reason: these files are local execution or tool-state drift and should not define the next refactor baseline.

## Checkpoint Strategy

1. Stage and commit SF/runtime closure baseline.
2. Stage and commit SF report retention archive separately.
3. Start the large refactor only after the focused smoke tests pass.
4. During the refactor, do not regenerate SF discovery artifacts unless the refactor changes SF contracts intentionally.
5. If a refactor changes runtime skill overlay behavior, rerun the current overlay smoke before claiming completion.

## Required Verification Before Refactor

- `python3 -m json.tool docs/reports/NEXUS_SF_REFACTOR_REQUIRED_SKILL_MANIFEST_2026-05-20.json`
- `python3 -m json.tool docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json`
- `uv run pytest tests/ops/test_build_sf_current_overlay_runtime_smoke.py tests/ops/test_build_sf_systematic_current_overlay.py tests/ops/test_build_sf_systematic_skill_tournament.py tests/ops/test_evaluate_github_skill_challengers.py tests/learning/test_skill_fit_ablation.py -q`

## Refactor Guardrails

- Keep runtime routing, skill discovery, promotion review, and public benchmark gates separate.
- Do not treat planner-selected skills as runtime-confirmed skills.
- Do not delete generated skill assets while current overlay references them.
- Do not use public benchmark artifacts as SF discovery evidence.
- Do not include local runtime report drift in refactor commits.
