# NEXUS SF Workspace Cleanup Index 2026-05-19

## Status

- Cleanup mode: non-destructive archive applied.
- Reason: SF reports reference evidence bundles and receipt roots under `/private/tmp`; deleting or moving those would break replayability.
- Public benchmark remains out of scope.

## Current Dirty Shape

- Modified tracked files: 10.
- SF/skill-fit report files kept at `docs/reports` root: 32.
- Superseded SF/skill-fit report files archived: 372.
- `/private/tmp/nexus_sf_*` evidence roots: 51.

## Keep As Current SF Closure Evidence

- `docs/reports/NEXUS_SF_FINAL_CLOSURE_V16_2026-05-19.json`
- `docs/reports/NEXUS_SF_FINAL_CLOSURE_V16_2026-05-19.md`
- `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V16_2026-05-19.json`
- `docs/reports/NEXUS_SF_POST_APPLY_POLICY_SMOKE_V16_2026-05-19.json`
- `docs/reports/NEXUS_SF_RUNTIME_RECEIPT_SMOKE_V16_2026-05-19.json`
- `docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_ROLLUP_2026-05-19.json`
- `docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_ROLLUP_2026-05-19.md`
- `docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_SKILL_FIT_CATALOG_2026-05-19.json`
- `docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_EXECUTION_MATRIX_2026-05-19.json`
- `docs/reports/NEXUS_SF_V16_RESIDUAL_SELECTION_SKILL_STATUS_2026-05-19.json`
- `docs/reports/NEXUS_SF_V15_HELD_CHALLENGER_ROLLUP_2026-05-19.json`
- `docs/reports/NEXUS_SF_V15_HELD_CHALLENGER_ROLLUP_2026-05-19.md`
- `docs/reports/NEXUS_SF_RUNTIME_PROMOTION_REVIEW_V15_2026-05-19.json`
- `docs/reports/NEXUS_SF_RUNTIME_POLICY_PATCH_PLAN_V15_2026-05-19.json`
- `docs/reports/NEXUS_SF_RUNTIME_POLICY_APPLY_GATE_V15_2026-05-19.json`
- `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V15_2026-05-19.json`

## Keep As Runtime Skill Assets

- `.agents/skills/sf2/`
- `.agents/skills/acceptance-evidence-failclosed/`
- `.agents/skills/create-plan/`
- `.agents/skills/cso/`
- `.agents/skills/gbrain-soul-audit/`
- `.agents/skills/research-citation-chain-verifier/`
- `.agents/skills/research-source-conflict-resolver/`
- `.agents/skills/research-source-validation-auditor/`

## Review Before Archive

- Older SF report generations from 2026-05-18.
- Earlier 2026-05-19 superseded reports: V12, V13, V14 intermediate artifacts.
- `/private/tmp/nexus_sf_v10_*` through `/private/tmp/nexus_sf_v16_*` roots.

## Do Not Auto-Clean

- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`: contains failure lessons required by AGENTS.
- `nexus/app/research_flow_service.py`, `nexus/engine/capability_planner.py`, `scripts/bench/capability_ab_runner.py`, and related tests: code changes need separate review before any revert.
- `/private/tmp/nexus_sf_v15_held_live_20260519` and `/private/tmp/nexus_sf_v16_residual_live_20260519`: latest receipt roots.

## Suggested Next Cleanup Action

Create a dedicated archive move plan for superseded SF reports, then move only reports that are not referenced by V16 closure, V16 overlay, V16 smoke, V16 rollup, or V15 rollup.

## Automated Retention Tool

- Dry-run command: `uv run python scripts/ops/build_sf_workspace_retention_plan.py --mode dry-run`
- Archive command: `uv run python scripts/ops/build_sf_workspace_retention_plan.py --mode archive`
- Latest dry-run after archive: scanned 32 SF/skill-fit reports, kept 32 current evidence files, marked 0 superseded reports as archive candidates, blocker count 0.
- Latest archive apply: moved 372 superseded SF/skill-fit reports across two archive passes, blocker count 0; one tracked report was restored and excluded from future archive plans.
- Plan output: `docs/reports/NEXUS_SF_WORKSPACE_RETENTION_PLAN_2026-05-19.json`
- Apply output: `docs/reports/NEXUS_SF_WORKSPACE_RETENTION_APPLY_RESULT_2026-05-19.json`
- Archive mode moves files under `docs/reports/archive/sf/<date>/`; it does not delete files and does not move `/private/tmp` receipt roots.
