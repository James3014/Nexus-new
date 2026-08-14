---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-63-scorecard-replay-contract
campaign_id: github-issue-63-learning-effectiveness-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/63
AUTO_CHAIN: false
reconciliation: TERMINAL_RECONCILIATION
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

## Terminal reconciliation (2026-08-14)

This card is terminal. Historical objective, baseline/dependencies, allowed
implementation files, required contract, forbidden scope, verification,
exit/claim ceiling, and block class above are preserved unchanged as the
implementation baseline.

- Issue #63: CLOSED/completed 2026-08-11T00:30:16Z. Owner receipt
  `5253012285` (`POST_MERGE_RECONCILIATION_20260811`) records disposition
  `PRODUCT_COMPLETE / STALE_CARD_ONLY` and authorizes exactly this two-card
  governance reconciliation.
- Dependency gate: Issue #82 / PR83 impact-map merge preceded the final PR80
  rebind, satisfying the `ISSUE82_IMPACT_MAP_SETTLE_THEN_PR80_EXACT_BASE_REVERIFY_GATE`.
- PR80: base `41e5ee06eeecb4abd7df7c15c36af13142a1da56` -> head
  `46b55c5a28c71e98e5bdd77f25f2b6064b64f70b` -> merge
  `b025f86a0456d9a7c892368e0fd0fab6d0607614`; delivered exactly
  `nexus/learning/learning_effectiveness_measurement.py` and
  `tests/learning/test_learning_effectiveness_measurement.py` plus this card
  and INDEX (4 files, +1362/-0); merged 2026-08-11T00:30:15Z; closes #63.
- PR80 head exact-base checks: 5/5 success (Pyright 31445937788, Wiki
  Governance 31445937753, Ruff 31445937745, Bandit 31445937759, Pytest
  31445937764). Tier 3 skipped. PR80 evidence: Task Card SHA-256
  `b5ce286dc94ae73c93f122906eea039f37597da3bb41b3233c44c74ad29385fa`;
  independent hostile review ACCEPT; `uv run pytest -q tests/learning` 293
  passed; dedicated hostile matrix 51 passed; `git diff --check` PASS.
- Current main `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`; merge ancestry
  verified via `git merge-base --is-ancestor`; reducer/tests remain present on
  current main.
- Marker: `LEARNING_EFFECTIVENESS_SCORECARD_REPLAYED`.
- Claim ceiling: deterministic observational replay only. This reconciliation
  does not prove measured or causal uplift, runtime integration, adaptation,
  route/policy improvement, Candidate acceptance, or production readiness, and
  grants no runtime, route, Workforce, provider, approval, integration, merge,
  release, or production authority.
