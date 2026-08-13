# Issue #65 Golden Witness Gate C

- campaign_id: github-issue-65-golden-witness-gate-c-20260814
- issue: #65
- authority: Ready Issue #65 test-only hardening under the Owner's standing coordinator grant; card preparation only
- owner: James Chen
- status: planned
- baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
- prerequisite: Gate B physically merged as PR #231 at the exact baseline above; Gate C mutation touching the shared self-hosted service test is serialized after PR #226
- current_frontier: 00-gate-c-semantic-consumer-tamper-witnesses.md
- AUTO_CHAIN: false
- maximum_files: 8
- claim_ceiling: GOLDEN_WITNESS_GATE_C_TASK_CARD_ONLY

## Scope lock

This card authorizes a later, separately executed Gate C test-only Candidate for
the eight Golden cases `GB-003`, `GB-006`, `GB-029`, `GB-030`, `GB-049`,
`GB-056`, `GB-072`, and `GB-073`. The later implementation may touch only the
six mapped test modules listed in the Task Card, plus this INDEX and that card.
This commit creates no tests and no product changes.

## Forbidden authority and scope

- No production, corpus, evaluator, documentation, manifest, workflow,
  route/Workforce/lifecycle authority, schema, or generated-artifact mutation.
- No approval, integration, merge, runtime, release, public/production claim,
  or lifecycle action authority.
- No work on Issues `#191` or `#143`.
- No wording-, enum-, serialization-, fixture-count-, default-, or shape-only
  assertions that could produce false greens; witnesses must exercise semantic
  consumers and hostile/tampered inputs.
- The shared `tests/nexus/orchestrator/test_self_hosted_task_service.py` slice
  is serialized after PR #226; no concurrent mutation is permitted.

## Exit

Stop at a card-only Candidate/Draft PR (if Issue authority permits that
artifact). Independent review and later implementation acceptance remain
required. This card does not self-accept, implement Gate C, or imply any
runtime, production, approval, integration, merge, or release truth.
