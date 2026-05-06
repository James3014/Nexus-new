# ADR: Runtime Route Reconcile Before Flash Promotion

## Context

Flash 8x1 can pass while route quality still regresses. In P820, two repair tasks solved successfully, but `runtime_pruning.with_nexus` stayed at `0.25` because the planner selected `autoreason` and `judge_panel` even when the route already estimated `candidate_factory.status=SKIPPED`.

## Decision

Repair tasks with a skipped candidate factory must not select ranking layers from low-confidence or generic evidence wording alone. They should use `hyper` and `repair_loop` until runtime produces multiple candidates. If runtime later proves `autoreason` actually ran successfully, receipt generation reconciles the plan by adding the executed capability before building receipts.

## Lesson

Planner estimates and runtime facts are different evidence classes. Flash should not be the first detector for this gap; pre-Flash Nexus self-tests must include route payload checks and runtime receipt reconciliation checks for candidate-factory skipped repair tasks.

## Verification

- Route payload self-test: repair + `candidate_factory.status=SKIPPED` no longer selects `autoreason` or `judge_panel`.
- Receipt self-test: actual runtime `autoreason.status=SUCCESS` adds an `autoreason` receipt even when the initial route estimate skipped ranking layers.
