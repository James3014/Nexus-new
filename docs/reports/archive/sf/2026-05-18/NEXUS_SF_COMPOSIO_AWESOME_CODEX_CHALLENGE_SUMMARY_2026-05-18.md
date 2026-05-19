# Nexus SF Composio Awesome Codex Skills Challenge Summary - 2026-05-18

Source: https://github.com/ComposioHQ/awesome-codex-skills @ `9c9da64cf1bbea611d43dd14a10788d55369b353`

Status: PASS
Screened skills: 880 total / 48 top-level / 832 automation-pack skipped
Compared capabilities: 6
Replace candidates: 1
Alternate candidates: 4
Keep current: 1
Reject: 0

Runtime update allowed: false
Public benchmark allowed: false

| Capability | Current skill | Challenger skill | Verdict | Current token delta | Challenger token delta | Current wall delta | Challenger wall delta |
|---|---|---|---:|---:|---:|---:|---:|
| forecast_pregate | `sf2-forecast_pregate-route-fit-spec` | `create-plan` | replace_candidate | -1554 | -6785 | 7.6163 | -19.3681 |
| registry_skills_sync | `sf2-registry_skills_sync-route-fit-spec` | `skill-creator` | alternate_candidate | 1035 | 750 | -49.1376 | -33.7727 |
| repair_loop | `test-driven-development` | `codebase-migrate` | alternate_candidate | 562 | 1464 | 19.1855 | 13.4121 |
| research_control_plane | `sf2-research_control_plane-route-fit-spec` | `content-research-writer` | alternate_candidate | 115 | -1414 | -39.1321 | -19.2867 |
| ui_validator | `sf2-ui_validator-route-fit-spec` | `webapp-testing` | alternate_candidate | 3163 | -4621 | 14.5879 | 19.9203 |
| ultra_review | `code-review-and-quality` | `pr-review-ci-fix` | keep_current | 1760 | 1929 | -13.2412 | 26.8824 |

## Interpretation

- Top-level Codex skills were screened first; the large `composio-skills/*-automation` pack was kept out of first-pass live because most entries require external app auth or service-specific action boundaries.
- Replace/alternate verdicts are observation-only SF evidence; they do not update runtime defaults.
- Runtime promotion and public benchmarks remain blocked until separate promotion review.
