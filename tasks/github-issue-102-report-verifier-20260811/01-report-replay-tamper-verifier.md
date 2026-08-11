# Task Card: Issue #102 R2B3 Report Replay and Tamper Verification

- task_id: github-issue-102
- issue: #102
- status: ACTIVE
- base_sha: 3c4f9065739e7a718bc27e1bf0d0113150946c60
- worker_role: luna_worker
- autonomy: bounded implementation
- target: /private/tmp/nexus-issue102-luna-019fee
- AUTO_CHAIN: false

## Objective

Strengthen `verify_benchmark_report()` so it deterministically rebuilds and
compares all claim-bearing report projections against authoritative run state
and fails closed on report, observation, packet, identity, run-manifest, or
comparison-schema tampering.

## Allowed files

Maximum two implementation/test files:

1. `nexus/research/epistemic_benchmark/report.py`
2. `tests/research/test_epistemic_benchmark_report.py`

Campaign authority artifacts are outside that ceiling.

## Required behavior

- Untouched authoritative report verifies true deterministically.
- Compare complete claim-bearing projection, including corpus/run identity,
  arm metrics, comparisons, coverage, limitations, source/private-context
  binding, and terminal metadata.
- Report-field tamper must fail even if the report hash is recomputed.
- Observation deletion/change, packet or run-manifest mutation,
  private-context substitution/staleness, comparison/paired-field tamper, and
  schema drift fail closed with deterministic bounded reasons.
- Verifier is read-only and repeated verification of identical state returns
  the same verdict/reasons.
- Preserve #101 ownership of `metrics.py`; consume but do not mutate its
  comparison schema.

## Forbidden scope

- `metrics.py`, metrics tests, observations, packets, contracts, benchmark
  artifacts, provider runs, routing, Workforce, lifecycle/runtime authority,
  docs/report outputs, approval, integration, release, or production mutation.
- If truth requires any forbidden file, stop `HARD_BLOCK`.

## Exact verification

```bash
uv run pytest -q tests/research/test_epistemic_benchmark_report.py
uv run pytest -q tests/research/test_epistemic_benchmark_metrics.py
uv run pytest -q tests/research/test_epistemic_benchmark_e2e.py
uv run ruff check \
  nexus/research/epistemic_benchmark/report.py \
  tests/research/test_epistemic_benchmark_report.py
uv run python -m compileall -q \
  nexus/research/epistemic_benchmark/report.py \
  tests/research/test_epistemic_benchmark_report.py
git diff --check
git diff --name-only 3c4f9065739e7a718bc27e1bf0d0113150946c60...HEAD
```

## Evidence and exit

- Hostile RED-to-GREEN witnesses for every tamper class.
- Two-file implementation scope, scoped commit, card SHA binding, independent
  review.
- Rebind after #101 settles and rerun report + metrics + e2e before acceptance.
- Claim ceiling: Candidate-level proof that the tested report/run-state
  tampering is rejected. No benchmark superiority, causality, provider,
  runtime, production, approval, release, or integration claim.

## Block classification

- `RECOVERABLE_BLOCK`: bounded verifier/test defect.
- `HARD_BLOCK`: need to mutate #101 schema or another forbidden authority,
  or inability to remain deterministic/read-only/fail-closed.
