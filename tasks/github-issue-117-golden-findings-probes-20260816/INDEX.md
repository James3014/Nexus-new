# Issue #117 — Golden Finding Executable Probes

- campaign_id: `github-issue-117-golden-findings-probes-20260816`
- issue: `#117`
- authority: Owner standing grant, bounded Ready Issue
- baseline_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- status: `ANALYSIS_PARALLEL_ONLY`
- frontier_status: `TASK_CARD_COMPILED_IMPLEMENTATION_NOT_AUTHORIZED` (GB-079)
- AUTO_CHAIN=false
- claim_ceiling: `probe_contract_and_evidence_only`

## Ordered Cards

1. [00-gb079-continuity-replay-probe.md](00-gb079-continuity-replay-probe.md) - `github-issue-117-gb079-continuity-replay-probe`

## Current Frontier

`github-issue-117-gb079-continuity-replay-probe`

## Completed Cards

(none)

## Blocked Cards

- GB-077 / GBF-002 -> Issue #12 (live Gateway identity)
- GB-078 / GBF-003 -> Issue #29 (same-task Online consumption)
- GB-080 / GBF-005 -> Issue #49 (World A final-claim delivery)

## GB-079 binding

GB-079 / GBF-004 (canonical task continuity) is the only Golden finding whose
owner evidence is physically settled. Issue #31 is CLOSED
`DONE_NO_FOLLOW_UP`; its implementation PR #245 merged as
`5853073a29cab5600187c9fa03728c8ee61ebe0a`, which is an ancestor of current
main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`. The merged contract exposes
`nexus/core/task_continuity.py`, `nexus/events/contracts.py`, and the
`self_hosted_task_service.py` attempt-event seam.

This INDEX compiles the CONTINUITY_REPLAY_PROBE contract only. No probe
implementation, no finding-to-covered conversion, and no product or test
mutation is authorized.

## Forbidden scope

- no second Golden evaluator runner; consume `scripts/ops/run_golden_behavior_eval.py`
  `PROBES` interface;
- no mutation of `tests/golden_behavior/corpus.py` or
  `tests/golden_behavior/test_corpus.py` (Issue #65 owned, open PR overlap);
- no new continuity/lifecycle/route/Workforce authority;
- no approval, integration, merge, release, runtime activation, or
  production/public claim;
- Issue #143, PR #228, PR #113 remain excluded.
