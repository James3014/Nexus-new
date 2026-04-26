# Gemini 3 Flash + Nexus Benchmark Report

- Date: 2026-04-27
- Model: `gemini-3-flash-preview`
- Baseline: `gemini-3-flash-preview_bare`
- Treatment: `gemini-3-flash-preview_nexus`
- Task set: `public_benchmark_pilot_v1`, `neutral_fixture`, 12 unique tasks x 2 trials
- History policy: `per_task_reset`

## Result

| Metric | Bare Gemini | Gemini + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Runs | 24 | 24 | 0 |
| Eligible runs | 23 | 24 | +1 |
| Solve rate | 83.3% | 100.0% | +16.7 pp |
| Semantic verified | 83.3% | 100.0% | +16.7 pp |
| Hard success | 91.7% | 100.0% | +8.3 pp |
| Trust mismatch | 0.0% | 0.0% | 0.0 pp |
| Avg wall time | 46.97s | 61.57s | +14.60s |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Token reliable rate | 95.7% | 91.7% | -4.0 pp |

## Nexus Wearing Evidence

| Evidence | Result |
| --- | ---: |
| Formal Nexus treatment valid | 24/24 |
| `gemini_uses_nexus=true` | 24/24 |
| `nexus_context_delivered=true` | 24/24 |
| five pillars active | 24/24 |
| six phases present | 24/24 |
| capability claim verified | 24/24 |
| Nexus rescue rate | 91.7% |

## What Improved

Nexus improved solve and semantic verification from 83.3% to 100.0% on this
12x2 neutral-fixture run. The lift came mainly from `test_repair`,
`ops_research`, and `refactor` tasks, while `bugfix`, `feature`, and
`docs_code_sync` were already solved by bare Gemini.

Gemini was still called in both arms: average model calls stayed at 1.00. This
supports the product interpretation that Nexus is a battlesuit around Gemini,
not a separate agent replacing Gemini.

## Current Cost

Nexus was slower in wall time: 61.57s vs 46.97s average. The likely cause is
bounded LLM/repair orchestration waiting even when local rescue wins. This is
now the main optimization target before making speed or efficiency claims.

Token/cost claims are not yet public-safe. Token reliability improved compared
with the earlier 2026-04-26 run, but Nexus still has estimated-token rows and
bare Gemini still has one `model_call_without_tokens` row.

## Evidence Files

- With Nexus: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/with_nexus_1777220242.jsonl`
- Bare Gemini: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/without_nexus_1777220242.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/evidence_bundle.json`
- Auto markdown: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/gemini_nexus_report_1777220242.md`

## Public-Safe Claim Draft

On a fixed 12-task neutral-fixture benchmark repeated twice, Gemini 3 Flash with
Nexus improved semantic solve rate from 83.3% to 100.0% while keeping trust
mismatch at 0.0%. The same benchmark also shows Nexus currently adds wall-time
overhead, so speed and token-cost claims require further telemetry hardening and
performance tuning.
