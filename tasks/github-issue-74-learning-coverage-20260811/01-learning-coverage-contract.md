# Task Card: Issue #74 Taxonomy-wide Learning Coverage

- task_id: github-issue-74
- issue: #74
- status: ACTIVE
- base_sha: e13ad5472296c8a303387f19662d19ce5a82bd0a
- worker_role: luna_worker
- autonomy: bounded implementation
- target: /private/tmp/nexus-issue74-luna-019fee
- AUTO_CHAIN: false

## Objective

Implement a deterministic, exact-source-bound coverage contract and bounded
observational probe pack for every row dynamically loaded from
`CAPABILITY_TAXONOMY`. Keep wiring, firing, proof, persistence, consumer use,
and verified outcome distinct and fail closed on missing or contradictory
evidence.

## Inputs and dependencies

- Issue #63 / PR #80 is physically closed and merged.
- Issue #82 is physically closed and merged.
- Source authority: `nexus/contracts/learning_experience.py::CAPABILITY_TAXONOMY`.
- Reuse-only references:
  - `nexus/learning/learning_episode_projection.py`
  - `nexus/learning/learning_closure_effectiveness.py`
  - `nexus/learning/learning_effectiveness_measurement.py`

## Allowed files

Maximum four implementation/test files:

1. `nexus/learning/learning_coverage_contract.py`
2. `nexus/learning/learning_coverage_probes.py`
3. `tests/learning/test_learning_coverage_contract.py`
4. `tests/learning/test_learning_coverage_probes.py`

This campaign INDEX and Task Card are authority artifacts outside that ceiling.

## Required behavior

- Derive the expected capability set dynamically; no duplicated hard-coded
  taxonomy authority.
- Produce exactly one deterministic row per capability.
- Represent W/F/P/S and source handles explicitly.
- Distinguish selected, invoked, evidence present, outcome, gate, persistence,
  consumer-shadow use, verifier proof, missingness, and claim ceiling.
- Reject duplicate/unknown capabilities, malformed levels, stale/tampered
  source binding, inconsistent evidence transitions, fabricated zeros, and
  unbounded/free-text evidence.
- Add observational probes only where source-backed evidence is available.
- Preserve the separate strict `memory_off/on` paired uplift signal.

## Forbidden scope

- Route, CapabilityPlanner, Workforce, policy, model, adapter, lifecycle,
  approval, promotion, release, integration, or production changes.
- Automatic adaptation, weighting, or effectiveness claims.
- Persistent reports or Learning Closure Matrix writeback.
- Changes to #63 measurement implementation or taxonomy authority.

## Exact verification

```bash
uv run pytest -q \
  tests/learning/test_learning_coverage_contract.py \
  tests/learning/test_learning_coverage_probes.py \
  tests/learning/test_learning_effectiveness_measurement.py \
  tests/learning/test_learning_closure_effectiveness.py

uv run ruff check \
  nexus/learning/learning_coverage_contract.py \
  nexus/learning/learning_coverage_probes.py \
  tests/learning/test_learning_coverage_contract.py \
  tests/learning/test_learning_coverage_probes.py

uv run python -m compileall -q \
  nexus/learning/learning_coverage_contract.py \
  nexus/learning/learning_coverage_probes.py \
  tests/learning/test_learning_coverage_contract.py \
  tests/learning/test_learning_coverage_probes.py

git diff --check
git diff --name-only e13ad5472296c8a303387f19662d19ce5a82bd0a...HEAD
```

## Evidence and exit

- RED then GREEN evidence for hostile missingness/tamper cases.
- Only allowed files changed; no deletions outside scope.
- Scoped commit bound to this card's SHA-256.
- Independent counter-review before push/PR.
- Maximum claim: deterministic exact-source taxonomy/evidence-level
  classification. No runtime learning uplift, causal effect, automatic
  adaptation, production readiness, approval, or integration claim.

## Block classification

- `RECOVERABLE_BLOCK`: tool/runtime/test infrastructure failure with intact scope.
- `HARD_BLOCK`: taxonomy authority conflict, required cross-scope mutation,
  ambiguous evidence semantics, or inability to remain fail closed.
