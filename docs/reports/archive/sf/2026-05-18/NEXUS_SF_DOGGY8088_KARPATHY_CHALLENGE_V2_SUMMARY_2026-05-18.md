# Nexus SF doggy8088 Karpathy Challenge Summary - 2026-05-18

Source: https://github.com/doggy8088/andrej-karpathy-skills @ `0bf99012a4e63f3370e8027215a715f1bed91059`

Status: PASS
Compared capabilities: 5
Replace candidates: 1
Alternate candidates: 2
Keep current: 2
Reject: 0

Runtime update allowed: false
Public benchmark allowed: false

| Capability | Current skill | Challenger alias | Verdict | Current token delta | Challenger token delta | Current wall delta | Challenger wall delta |
|---|---|---|---:|---:|---:|---:|---:|
| codeintel | `sf2-codeintel-route-fit-spec` | `karpathy-guidelines__codeintel` | keep_current | -1312 | 4135 | 9.142 | 39.7441 |
| direct_master_loop | `sf2-direct_master_loop-route-fit-spec` | `karpathy-guidelines__direct_master_loop` | keep_current | -6314 | 3318 | -78.7746 | 31.592 |
| hyper_sprint | `sf2-hyper_sprint-route-fit-spec` | `karpathy-guidelines__hyper_sprint` | alternate_candidate | -360 | -7888 | -11.9126 | 13.212 |
| repair_loop | `test-driven-development` | `karpathy-guidelines__repair_loop` | replace_candidate | 562 | -904 | 19.1855 | -5.1138 |
| ultra_review | `code-review-and-quality` | `karpathy-guidelines__ultra_review` | alternate_candidate | 1760 | -1745 | -13.2412 | 14.6483 |

## Interpretation

- `karpathy-guidelines` is a single canonical external skill represented with per-capability ablation aliases because the current catalog policy stores one capability mount per skill id.
- Replace/alternate verdicts are observation-only SF evidence; they do not update runtime defaults.
- V1 report is preserved as the failure artifact showing why per-capability aliasing is required.
