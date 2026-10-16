# Gemini 3 Flash + Nexus P378 Smoke Report

## Task

Run a small same-model Gemini Flash A/B after P363-P377 gate hardening. This is a
regression/sanity run, not a public uplift candidate.

## Configuration

- Model: `gemini-3-flash-preview`
- Scope: 4 tasks x 1 trial
- Dataset: `scripts/bench/public_benchmark_rlm_harder_v2.json`
- Task IDs:
  - `rlm-harder-v2-governance-001`
  - `rlm-harder-v2-evidence-001`
  - `rlm-harder-v2-belief-001`
  - `rlm-harder-v2-memory-001`
- Hidden verifier: enabled
- Same model lock: pass
- Evidence bundle: enabled
- Nexus runner: subprocess

## Results

| Metric | Bare Flash | Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Eligible rows | 4/4 | 4/4 | n/a |
| Semantic verified | 50.0% | 50.0% | 0.0pp |
| Trust mismatch | 0.0% | 0.0% | 0.0pp |
| Avg wall time | 15.41s | 76.83s | +61.42s |
| Avg model calls | 1.00 | 2.00 | +1.00 |
| Avg tokens | 42131 | 90852 | +48721 |
| RLM trace present | 0.0% | 100.0% | +100.0pp |

## Route Quality

| Metric | Flash + Nexus | Gate | Verdict |
| --- | ---: | ---: | --- |
| Selected -> Invoked | 78.4% | >= 70.0% | PASS |
| Invoked -> Evidence | 95.0% | >= 95.0% | PASS |
| Evidence -> Outcome | 65.8% | >= 90.0% | FAIL |
| Unnecessary Selected | 21.6% | <= 30.0% | PASS |

## Gate Verdict

- Public claim gate: FAIL
- Public delivery gate: FAIL
- Evidence bundle public cost gate: FAIL
- Performance claim gate in generated markdown: PASS, but this is not enough for
  a public Nexus claim because delivery/wearing gates failed.

Main failures:

- `claim_verified_below_threshold`
- `nexus_usage_valid_below_threshold`
- `nexus_wearing_below_threshold`
- `research_gate_missing`
- `route_quality_evidence_to_outcome_below_threshold`
- `expected_capability_not_public_safe` for expected task capabilities

## Evidence

- Preflight: `.nexus/reports/bench_gemini3flash_p378_smoke4/benchmark_preflight.json`
- With Nexus JSONL: `.nexus/reports/bench_gemini3flash_p378_smoke4/with_nexus_1778064036.jsonl`
- Bare JSONL: `.nexus/reports/bench_gemini3flash_p378_smoke4/without_nexus_1778064036.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_p378_smoke4/evidence_bundle.json`
- Generated report: `.nexus/reports/bench_gemini3flash_p378_smoke4/gemini_nexus_report_1778064036.md`
- Enforced report: `.nexus/reports/bench_gemini3flash_p378_smoke4/gemini_nexus_report_manual_enforced.md`

## Decision

Do not expand to 8x2 yet. The next optimization should target evidence-to-outcome
conversion and Nexus usage validity, not solve-rate chasing.
