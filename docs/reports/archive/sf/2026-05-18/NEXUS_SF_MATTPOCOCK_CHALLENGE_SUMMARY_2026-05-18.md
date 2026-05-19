# SF Matt Pocock Skills Challenge - 2026-05-18

Repo: https://github.com/mattpocock/skills
Commit: e74f0061bb67222181640effa98c675bdb2fdaa7

## Summary

Active skills screened: 14
Routed candidates: 14
Live challengers: 6
Replace candidates: 2
Alternate candidates: 2
Keep current: 2

Runtime update allowed: false
Public benchmark allowed: false

## Live comparison

| Capability | Current skill | Matt candidate | Recommendation | Token delta current -> candidate | Wall delta current -> candidate |
|---|---|---|---:|---:|---:|
| codeintel | `sf2-codeintel-route-fit-spec` | `improve-codebase-architecture` | keep_current | -1312 -> -192 | 9.142 -> 22.3514 |
| forecast_pregate | `sf2-forecast_pregate-route-fit-spec` | `to-prd` | replace_candidate | -1554 -> -2876 | 7.6163 -> 0.9027 |
| registry_skills_sync | `sf2-registry_skills_sync-route-fit-spec` | `write-a-skill` | alternate_candidate | 1035 -> 999 | -49.1376 -> -18.6293 |
| repair_loop | `test-driven-development` | `tdd` | replace_candidate | 562 -> -21155 | 19.1855 -> -67.7477 |
| research_control_plane | `sf2-research_control_plane-route-fit-spec` | `grill-with-docs` | alternate_candidate | 115 -> -702 | -39.1321 -> -23.0889 |
| xray | `sf2-xray-route-fit-spec` | `diagnose` | keep_current | 3920 -> 5869 | 21.5001 -> 36.7877 |

## Interpretation

- `repair_loop`: `tdd` is a strong replace candidate versus `test-driven-development` in this bounded Flash+Nexus pair.
- `forecast_pregate`: `to-prd` is a replace candidate versus the SF2 route-fit spec in this bounded pair.
- `registry_skills_sync`: `write-a-skill` is an alternate; token delta is slightly better, wall delta is worse than current.
- `research_control_plane`: `grill-with-docs` is an alternate; token delta is better, wall delta is worse than current.
- `codeintel` and `xray`: keep current pairings for now.

## Next gate

Replacement is catalog-level only. Before runtime promotion, run a follow-up seal with at least 3 task variants for `repair_loop/tdd` and `forecast_pregate/to-prd`, plus negative-control fail-closed checks.
