# Nexus SF External Skill Update Record - 2026-05-18

Status: PASS
Runtime update allowed: false
Public benchmark allowed: false

## Selected updates

| Capability | Selected candidate | State | Source | Runtime update |
|---|---|---|---|---|
| codeintel | keep current | keep_current | - | false |
| direct_master_loop | keep current | keep_current | - | false |
| forecast_pregate | `create-plan` | catalog_replace_ready | ComposioHQ/awesome-codex-skills | false |
| hyper_sprint | `karpathy-guidelines__hyper_sprint` | alternate_materialization_required | doggy8088/andrej-karpathy-skills | false |
| registry_skills_sync | `skill-creator` | alternate_materialization_required | ComposioHQ/awesome-codex-skills | false |
| repair_loop | `tdd` | catalog_replace_ready | mattpocock/skills | false |
| research_control_plane | `content-research-writer` | alternate_materialization_required | ComposioHQ/awesome-codex-skills | false |
| ui_validator | `webapp-testing` | alternate_materialization_required | ComposioHQ/awesome-codex-skills | false |
| ultra_review | `karpathy-guidelines__ultra_review` | alternate_materialization_required | doggy8088/andrej-karpathy-skills | false |
| xray | keep current | keep_current | - | false |

## Replacement log

| Capability | Replacement candidate | State | Evidence |
|---|---|---|---|
| forecast_pregate | `create-plan` | catalog_replace_ready | `docs/reports/NEXUS_SF_COMPOSIO_AWESOME_CODEX_CHALLENGE_COMPARISON_2026-05-18.json` |
| repair_loop | `tdd` | catalog_replace_ready | `docs/reports/NEXUS_SF_MATTPOCOCK_CHALLENGE_COMPARISON_2026-05-18.json` |

## Boundary

- This record updates SF catalog intent only; it does not write runtime defaults.
- Runtime promotion requires separate review after repo-local materialization and seal validation.
- Public benchmark remains blocked until runtime update and benchmark readiness gates pass.
