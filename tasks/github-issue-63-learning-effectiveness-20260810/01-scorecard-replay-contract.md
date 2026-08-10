---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-63-scorecard-replay-contract
campaign_id: github-issue-63-learning-effectiveness-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/63
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Identity-bound Learning Effectiveness Scorecard Replay

## Objective

Implement `nexus.learning_effectiveness_measurement.v1` as a deterministic,
fail-closed reducer over immutable, identity-complete attempt rows. Keep base
observational metrics separate from the stricter paired `memory_off/on` uplift
signal.

## Baseline and dependencies

- GitHub main: `84eaa6886e0388a4e15f5b837c89e37768b14307`.
- Issue #46 / PR #50 Golden corpus is physically settled.
- #69 is read-only predecessor evidence and remains separate from this work.
- Active #7, PR #70, and PR #71 have no path overlap with this card.

## Allowed implementation files

- `nexus/learning/learning_effectiveness_measurement.py`
- `tests/learning/test_learning_effectiveness_measurement.py`

Maximum implementation/test paths changed: 2. This Task Card and campaign
index are authority artifacts and do not widen implementation scope.

## Required contract

- require `task_fingerprint`, `task_id`, `attempt_id`, `attempt_index`,
  `action_id`, source revision/tree, verifier status/artifact/hash, memory arm,
  retrieved lesson IDs, applied-attributed lesson IDs, terminal outcome,
  measured elapsed time, intervention events/count, forbidden-strategy identity
  and violation event, plus explicit missingness/ineligibility reasons;
- preserve immutable input rows and reject duplicate/colliding identities;
- deterministically compute failure recurrence, first-pass qualification,
  attempts-to-green, time-to-green, intervention rate/count, forbidden-strategy
  violation rate, and retrieved-to-applied-to-qualified-useful funnel;
- every metric records numerator, denominator, eligible row count, missing
  telemetry count, exclusions, and claim ceiling;
- never coerce missing data to zero or success;
- keep paired `memory_off/on` uplift separate and require matching task
  fingerprint, failing off arm, passing on arm, and both artifact/receipt sets;
- all output is observational/shadow evidence only.

## Forbidden scope

- no edits to existing runtime producers, writers, ledgers, projections,
  receipts, planners, gateways, lifecycle, route, Workforce, policy, model,
  adapter, approval, promotion, release, or production code;
- specifically do not edit `unified_runtime.py`, `receipt_base.py`,
  `learning_experience.py`, `learning_episode_projection.py`,
  `learning_closure_effectiveness.py`, `learning_closure_bridge.py`, or any #7
  file;
- no generated report or ledger writeback;
- no automatic adaptation, public causal claim, or hidden chain-of-thought.

## Verification

```text
uv run pytest -q -p no:cacheprovider tests/learning/test_learning_effectiveness_measurement.py
uv run pytest -q -p no:cacheprovider tests/learning/test_learning_closure_effectiveness.py tests/learning/test_learning_episode_projection.py tests/learning/test_nexus_learning_episode_contract.py
git diff --check
```

Tests must include identity/missingness/tamper/duplicate rejection, deterministic
input-order replay, immutable inputs, no fabricated zero, complete metric
denominators, paired-uplift separation, and no authority/adaptation side effect.

## Exit and claim ceiling

The two allowed files implement and verify deterministic observational replay,
an independent exact-diff review accepts the result, and no forbidden file or
authority changes. The maximum claim is contract replay correctness over
supplied identity-complete rows. Do not claim measured uplift, runtime
integration, policy improvement, route improvement, or production readiness.

## Block class

`RECOVERABLE_BLOCK` for environment/test infrastructure failures.
`HARD_BLOCK` for missing identity semantics, required edits outside the two
allowed implementation files, or any request to weaken the claim boundary.
