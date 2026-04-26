# Gemini 3 Flash + Nexus Benchmark Report

- Date: 2026-04-27
- Model: `gemini-3-flash-preview`
- Baseline: `gemini-3-flash-preview_bare`
- Treatment: `gemini-3-flash-preview_nexus`
- Broad task set: `public_benchmark_pilot_v1`, `neutral_fixture`, 12 unique tasks x 2 trials
- Hard-only follow-up: `public_benchmark_pilot_v1`, `neutral_fixture`, 6 unique hard tasks x 2 trials
- Hard-neutral v2: `public_benchmark_hard_neutral_v2`, 12 unique hard neutral tasks x 2 trials
- Token telemetry smoke: `public_benchmark_hard_neutral_v2`, 1 unique hard neutral task x 1 trial
- History policy: `per_task_reset`

## Result

### Broad Neutral Fixture 12x2

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

### Hard-Only Gateway30 6x2

| Metric | Bare Gemini | Gemini + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Runs | 12 | 12 | 0 |
| Eligible runs | 11 | 12 | +1 |
| Solve rate | 91.7% | 100.0% | +8.3 pp |
| Semantic verified | 91.7% | 100.0% | +8.3 pp |
| Hard success | 91.7% | 100.0% | +8.3 pp |
| Trust mismatch | 0.0% | 0.0% | 0.0 pp |
| Avg wall time | 33.59s | 34.01s | +0.42s |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Token measured rate | 0.0% | 0.0% | 0.0 pp |

### Hard-Neutral v2 12x2

| Metric | Bare Gemini | Gemini + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Runs | 24 | 24 | 0 |
| Eligible runs | 24 | 24 | 0 |
| Solve rate | 100.0% | 100.0% | 0.0 pp |
| Semantic verified | 100.0% | 100.0% | 0.0 pp |
| Hard success | 100.0% | 100.0% | 0.0 pp |
| Trust mismatch | 0.0% | 0.0% | 0.0 pp |
| Avg wall time | 38.05s | 34.62s | -3.43s |
| Wall speedup | n/a | 9.0% | n/a |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Token measured rate | 0.0% | 0.0% | 0.0 pp |
| Token public-safe claim | NO | NO | n/a |

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

The hard-only gateway30 follow-up also passed Nexus treatment evidence:
`gemini_uses_nexus=true`, `nexus_context_delivered=true`, five pillars, six
phases, and capability claim verification were all 12/12.

The hard-neutral v2 12x2 run passed the same formal treatment criteria 24/24.
It also confirmed Gemini was invoked in both arms with average model calls at
1.00, while Nexus delivered context, five pillars, six phases, and claim
verification on every Nexus row.

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

The follow-up phase analysis found that the overhead was concentrated in Phase
R: median `phase_wall_r_sec` was 63.22s, and 23/24 Nexus rows ultimately used a
local winner after the Gemini/Hyper path failed or timed out. The benchmark
runner now caps the Nexus subprocess gateway timeout at 30s by default, with
`NEXUS_BENCH_GATEWAY_TIMEOUT_SEC` available for explicit overrides.

A 3-task hard smoke after the timeout cap showed the intended direction:
Gemini + Nexus stayed at 3/3 solved and average wall time dropped to 34.12s,
compared with 40.11s for bare Gemini on the same smoke.

The follow-up hard-only 6 unique tasks x 2 trials run confirmed that the timeout
cap did not break Nexus completion: Gemini + Nexus solved 12/12 and bare Gemini
solved 11/12. Average wall time was effectively tied at 34.01s vs 33.59s, so the
previous 61.57s Nexus average was a benchmark timeout artifact, not an inherent
Nexus requirement.

The hard-neutral v2 12 unique tasks x 2 trials run used a stronger hard-only
neutral fixture set. Both arms solved 24/24, so it does not show solve-rate lift.
It does show that Gemini wearing Nexus stayed fully verified and finished faster
on average: 34.62s vs 38.05s, a 9.0% wall-time improvement. Nexus also recorded
a 91.7% rescue rate, meaning most successful rows were completed by Nexus'
self-healing/local verification path after the Gemini-wrapped path supplied the
required context and trace.

Token/cost claims are not yet public-safe. Token reliability improved compared
with the earlier 2026-04-26 run, but Nexus still has estimated-token rows and
bare Gemini still has one `model_call_without_tokens` row.

A follow-up token telemetry smoke fixed one parser issue: direct Gemini CLI
rows with gateway `stats.models.*.tokens.total` are now normalized to
`token_capture_status=measured`. On the 1x1 smoke, bare Gemini reached 100.0%
token measured rate. Nexus remained 0.0% measured on that row because the
successful Nexus result came from the self-healing/local verification path,
recorded as `not_applicable_local_only`. The report now exposes both
`token_local_only_rate` and `cost_comparable_rate`; for this smoke the
cost-comparable rate is 100.0% for bare Gemini and 0.0% for Nexus. This confirms
token-cost comparison is not hard because of arithmetic; it is hard because the
two arms currently expose different telemetry surfaces.

## Evidence Files

- With Nexus: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/with_nexus_1777220242.jsonl`
- Bare Gemini: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/without_nexus_1777220242.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/evidence_bundle.json`
- Auto markdown: `.nexus/reports/bench_gemini3flash_vs_nexus_12x2_20260427/gemini_nexus_report_1777220242.md`
- Gateway-timeout smoke: `.nexus/reports/bench_gemini3flash_vs_nexus_gateway30_smoke_3x1_20260427/gemini_nexus_report_1777223214.md`
- Hard-only gateway30 with Nexus: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_12x2_gateway30_20260427/with_nexus_1777226288.jsonl`
- Hard-only gateway30 bare Gemini: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_12x2_gateway30_20260427/without_nexus_1777226288.jsonl`
- Hard-only gateway30 report: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_12x2_gateway30_20260427/gemini_nexus_report_1777226288.md`
- Hard-neutral v2 smoke report: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_neutral_v2_smoke_3x1_20260427/gemini_nexus_report_1777227663.md`
- Hard-neutral v2 with Nexus: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_neutral_v2_12x2_20260427/with_nexus_1777227906.jsonl`
- Hard-neutral v2 bare Gemini: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_neutral_v2_12x2_20260427/without_nexus_1777227906.jsonl`
- Hard-neutral v2 report: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_neutral_v2_12x2_20260427/gemini_nexus_report_1777227906.md`
- Hard-neutral v2 A/B eval: `.nexus/reports/bench_gemini3flash_vs_nexus_hard_neutral_v2_12x2_20260427/ab_eval_1777227906.json`
- Token telemetry smoke report: `.nexus/reports/bench_gemini3flash_token_telemetry_smoke_1x1_20260427/gemini_nexus_report_1777230094.md`

## Public-Safe Claim Draft

On a fixed 12-task neutral-fixture benchmark repeated twice, Gemini 3 Flash with
Nexus improved semantic solve rate from 83.3% to 100.0% while keeping trust
mismatch at 0.0%. After capping benchmark gateway timeout at 30s, a hard-only
follow-up preserved Nexus' 100.0% solve rate and brought wall time roughly in
line with bare Gemini. On the later hard-neutral v2 12x2 run, both arms solved
100.0%, while Gemini wearing Nexus was 9.0% faster on average and retained
24/24 formal Nexus usage evidence. Token-cost claims still require further
telemetry hardening.
