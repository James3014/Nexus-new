# Task Card 00: EIA Open-SWE Unattended Canary (2026-10-12)

## Identity

- task_id: `eia-open-swe-canary-20261012`
- campaign_id: `external-intelligence-open-swe-canary-20261012`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false
- allow_deletions: false

## Lineage / replay fence

This is a fresh execution identity for the open-swe canary Issue. It does not
retry, overwrite, or reinterpret Issue #349 or Issue #530 executions. The unit
identity is also fresh so the fanout receipt store cannot reuse an older
`task_id + unit_id` key.

Dispatch-time main authority is not encoded as a mutable card-local SHA. The
runtime must bind this exact raw Git blob through the Issue's fenced contract:
`main_sha` selects the canonical commit and `task_card_hash` is the SHA-256 of
this exact raw blob at that commit. Issue `task_id` must equal this card's
`task_id`.

## Objective

Add one harmless unit test file containing a single trivially true assertion,
proving the External Intelligence Automation daemon rebuilt on M4 on
2026-10-12 can discover, validate, execute, verify, and publish one approved
Task Card unattended with `semantic_backend=open_swe` and
`worker_backend=open_swe`.

This card exists solely to exercise the live chain once:

daemon natural polling -> targeted remote-main refresh -> exact-main Task Card
authority validation -> open-swe semantic compilation -> open-swe worker
execution -> deterministic verification/closure -> exactly-once GitHub
publication -> stop at independent acceptance.

## Allowed files

- `tests/ops/test_external_intelligence_open_swe_canary_20261012.py`

## Required implementation

Create exactly the allowed test file with one test function whose only behavior
is a trivially true assertion. Do not alter any existing test or production
source file.

## Forbidden scope

No canonical-runtime mutation by the worker; no changes to
AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/SOUL/Cursor bootstrap files; no production
source, workflow, route, policy, provider, credential, Task Card, Issue, or
control-plane changes; no second selector/router/planner authority; no
deletions; no release or production claims; no manual `run-once` substitute;
no mutation, deletion, reset, or reinterpretation of historical EIA durable
attempt/session/receipt state.

## Verification commands

```bash
python3 -m pytest -q tests/ops/test_external_intelligence_open_swe_canary_20261012.py
git diff --check
git diff --name-status --diff-filter=D
```

## Worker binding

The worker is whatever the canonical planner seam binds for the configured
open-swe backend. This card creates no model-selection authority and pins no
provider or model.

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants
no approval, merge, integration, release, production, or autonomous follow-on
authority.
