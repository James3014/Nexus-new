# Gemini 3 Flash + Nexus Benchmark Report

Date: 2026-04-26

## Executive Summary

This report compares `Gemini 3 Flash bare` with `Gemini 3 Flash + Nexus` on the
same neutral fixture benchmark tasks. In this setup, Nexus is the battlesuit
Gemini wears: Gemini is still invoked (`model_calls > 0`), while Nexus provides
context delivery, routing, governance, repair loops, and evidence verification.
Nexus is not counted as a separate agent solving instead of Gemini.

The primary formal result is the 12-task run:

| Metric | Gemini 3 Flash bare | Gemini 3 Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Eligible rows | 12/12 | 12/12 | 0 infra invalid |
| Solve rate | 10/12 = 83.3% | 12/12 = 100.0% | +16.7 pp |
| Semantic verified | 10/12 = 83.3% | 12/12 = 100.0% | +16.7 pp |
| First-pass rate | 10/12 = 83.3% | 12/12 = 100.0% | +16.7 pp |
| Trust mismatch | 0/12 = 0.0% | 0/12 = 0.0% | no regression |
| Avg wall time | 41.50s | 33.99s | 18.1% faster |
| Avg model calls | 1.0 | 1.0 | same |

Interpretation: on this 12-task neutral fixture run, Nexus improved Gemini 3
Flash by +16.7 percentage points in solve rate and semantic verification, while
using the same average number of model calls and lower average wall time.

## Run Set

| Run | Scope | Bare solve | Nexus solve | Lift | Bare wall | Nexus wall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Smoke 3x1 | neutral fixture | 1/3 = 33.3% | 3/3 = 100.0% | +66.7 pp | 44.63s | 35.38s |
| Smoke 6x1 | neutral fixture | 4/6 = 66.7% | 6/6 = 100.0% | +33.3 pp | 49.72s | 34.24s |
| Formal 12x1 | neutral fixture | 10/12 = 83.3% | 12/12 = 100.0% | +16.7 pp | 41.50s | 33.99s |

The 12-task run is the most reliable of the three because it has the largest
sample. The smaller smoke runs are useful as a quota and harness validation
trail, not as the headline claim.

## Wearing Evidence

For the formal 12-task run, all Nexus rows met the wearing contract:

| Evidence field | Result |
| --- | ---: |
| `run_eligible` | 12/12 |
| `model_calls > 0` | 12/12 |
| `gemini_uses_nexus=true` | 12/12 |
| `nexus_context_delivered=true` | 12/12 |
| Five pillars observed | 12/12 |
| Six phases observed | 12/12 |
| `nexus_usage_valid=true` | 12/12 |
| `capability_claim_verified=true` | 12/12 |
| `nexus_rescued=true` | 11/12 |

Five pillars means LanceDB, Memory, MemPalace, Belief, and Artifact were all
observed. Six phases means P, X, D, R, A, and C were all observed.

## What Nexus Improved

Nexus improved the run through the following mechanisms:

- Context delivery: Gemini received Nexus context before solving.
- Governance: MemPalace and completion checks kept reports aligned with verified outcomes.
- Routing and repair: Hyper/self-heal flows were used when the direct Gemini patch path was insufficient.
- Evidence closure: artifacts and tests verified claims before marking a task complete.
- Trust consistency: no row reported success with a semantic failure.

The strongest signal is that the average model call count stayed the same
(`1.0 -> 1.0`) while solved tasks increased (`10/12 -> 12/12`). Nexus did not
win by simply calling Gemini more often in this run.

## Token Reliability

Token data is not suitable for public claims yet.

| Run | Token reliable rows |
| --- | ---: |
| Bare 12x1 | 11/12 |
| Nexus 12x1 | 1/12 |

The new benchmark field `token_reliable` marks rows where token accounting can
be trusted. Most Nexus rows currently report `model_call_without_tokens`, so
token savings should not be claimed from these runs. Solve rate, semantic
verification, wall time, model calls, and wearing evidence are the reliable
metrics in this report.

## Evidence Files

Formal 12-task run:

- With Nexus: `.nexus/reports/bench_gemini3flash_vs_nexus_formal_12x1_20260426/with_nexus_1777218125.jsonl`
- Bare Gemini: `.nexus/reports/bench_gemini3flash_vs_nexus_formal_12x1_20260426/without_nexus_1777218125.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_vs_nexus_formal_12x1_20260426/evidence_bundle.json`

Smoke runs:

- 3x1: `.nexus/reports/bench_gemini3flash_vs_nexus_smoke_3x1_20260426/`
- 6x1: `.nexus/reports/bench_gemini3flash_vs_nexus_smoke_6x1_20260426/`

## Public-Safe Claim Draft

On a 12-task neutral fixture benchmark run on 2026-04-26, Gemini 3 Flash with
Nexus improved verified solve rate from 83.3% to 100.0% (+16.7 percentage
points) with no trust mismatches and the same average number of model calls
(1.0). Every Nexus row showed Gemini wearing Nexus context with all five
pillars and all six phases observed. Token savings are not claimed because
Nexus token capture is not yet reliable.

## Limits

- Sample size is still small: 12 tasks.
- Tasks are neutral fixtures, not a full external public benchmark.
- Results should not be generalized to every repository or task type yet.
- Token accounting is explicitly marked unreliable for most Nexus rows.
- More trials are needed to stabilize confidence intervals.

## Recommended Next Step

Run an 18-task or repeated-trial benchmark only after deciding whether to spend
more Gemini quota now. If quota should be conserved, the next best engineering
step is to fix Nexus token capture so future public reports can include reliable
cost metrics.
