# Task Card: Issue #101 True Paired R2B2 Metrics

- task_id: github-issue-101
- issue: #101
- status: COMPLETE / TERMINAL_RECONCILIATION
- historical_baseline: e13ad5472296c8a303387f19662d19ce5a82bd0a
- reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
- current_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
- worker_role: luna_worker
- autonomy: bounded implementation
- target: /private/tmp/nexus-issue101-luna-019fee
- AUTO_CHAIN: false
- terminal_marker: R2B2_TRUE_PAIRED_METRICS_PROVEN
- claim_ceiling: repository-contained paired metrics source/tests only

## Objective

Replace the R2B2 `min(observed_cases)` proxy and full-arm aggregate deltas with
true exact-pair intersection metrics. Surface explicit paired denominators and
missingness without changing report, observation-import, packet, or contract
authorities.

## Inputs and dependencies

- Issue #100 observation-integrity gate is accepted.
- Issue #101 is independently implementable from #102.
- Exact source blobs at task start:
  - `nexus/research/epistemic_benchmark/metrics.py`
  - `tests/research/test_epistemic_benchmark_metrics.py`

## Allowed files

Maximum two implementation/test files:

1. `nexus/research/epistemic_benchmark/metrics.py`
2. `tests/research/test_epistemic_benchmark_metrics.py`

This campaign INDEX and Task Card are authority artifacts outside that ceiling.

## Required behavior

- Build the paired population from exact compatible case identities present in
  both compared arms.
- Compute pairwise success, latency, cost, and intervention deltas only from
  that exact intersection.
- Expose paired denominator and explicit arm-specific/unpaired missingness.
- Preserve deterministic ordering and existing compatible output fields where
  truthful.
- Reject duplicate/colliding identities, malformed observations, incompatible
  pairing keys, and fabricated zero denominators.
- Add hostile RED-to-GREEN tests proving full-arm aggregates cannot leak into
  paired deltas.

## Forbidden scope

- Report renderer/source, observation import, contracts, packets, persisted
  benchmark artifacts, workflows, routing, learning, policy, or runtime mutation.
- Benchmark-superiority, causal, production, release, approval, or integration claims.
- Silent schema expansion outside the two allowed files. If report
  compatibility requires another file, stop `HARD_BLOCK`.

## Exact verification

```bash
uv run pytest -q tests/research/test_epistemic_benchmark_metrics.py
uv run pytest -q tests/research/test_epistemic_benchmark_report.py
uv run ruff check \
  nexus/research/epistemic_benchmark/metrics.py \
  tests/research/test_epistemic_benchmark_metrics.py
uv run python -m compileall -q \
  nexus/research/epistemic_benchmark/metrics.py \
  tests/research/test_epistemic_benchmark_metrics.py
git diff --check
git diff --name-only e13ad5472296c8a303387f19662d19ce5a82bd0a...HEAD
```

## Evidence and exit

- Record the failing pre-fix hostile tests and passing post-fix results.
- Only allowed files changed; no unauthorized deletion.
- Scoped commit bound to the card SHA-256.
- Independent review before push/PR.
- Maximum claim: exact paired population/deltas and explicit missingness for
  R2B2. No benchmark superiority or production readiness.

## Block classification

- `RECOVERABLE_BLOCK`: test/tool infrastructure failure.
- `HARD_BLOCK`: report/schema authority conflict, required cross-scope edit,
  ambiguous pairing identity, or inability to fail closed.

## Terminal reconciliation

Completed by PR #108: exact head
`ce7e40ed99deece77cc587d6dd729faed527751a`, merge
`4437d34afc78b247354fbd0d2c1d7bf0d2fdf4c9`, reconciled on current `main`
`12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`. Required checks succeeded with
Tier3 skipped as expected; Owner terminal receipt comment `5282536716`; 65
zero-provider focused tests passed on current main (metrics and report suites).
Historical baseline `e13ad5472296c8a303387f19662d19ce5a82bd0a`, the two-file
implementation ceiling, and the forbidden-scope boundary are preserved
unchanged.

`R2B2_TRUE_PAIRED_METRICS_PROVEN` is limited to the repository-contained true
paired R2B2 metrics source and tests. It grants no benchmark-superiority,
causal, provider, execution, release, integration, runtime, or production
authority. Issue #100 observation-integrity, #102 report verifier, and #103
execution-topology boundaries remain separate and are not activated here.
`AUTO_CHAIN=false`.
