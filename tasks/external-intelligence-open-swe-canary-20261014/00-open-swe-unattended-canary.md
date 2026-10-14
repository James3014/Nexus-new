# Task Card 00: EIA Open-SWE Unattended Canary, ChatGPT Team / GPT-5.6 transport (2026-10-14)

## Identity

- task_id: `eia-open-swe-canary-20261014`
- campaign_id: `external-intelligence-open-swe-canary-20261014`
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
- execution_lane: `DIRECT_DELEGATED`
- capability_disposition: `EXTEND_EXISTING`
- capability_ids: `chatgpt_web_semantic_transport, nexus_governance_and_capability_planning`

## Lineage / replay fence

This is a fresh execution identity. It does not retry, overwrite, or reinterpret
Issue #349, Issue #530, Issue #1828, or the cards `eia-open-swe-canary-20261012`,
`eia-open-swe-canary-20261013` and `eia-open-swe-canary-20261013b` (the latter's
candidate was integrated by #2081). On 2026-10-14 the owner moved the EIA ChatGPT
Web transport to the owner's ChatGPT Team workspace with GPT-5.6 Sol at the
highest reasoning effort; this card exercises the full chain once on that
transport. The unit identity is fresh so the fanout receipt store cannot reuse an
older `task_id + unit_id` key.

Dispatch-time main authority is not encoded as a mutable card-local SHA. The
runtime must bind this exact raw Git blob through the Issue's fenced contract:
`main_sha` selects the canonical commit and `task_card_hash` is the SHA-256 of
this exact raw blob at that commit. Issue `task_id` must equal this card's
`task_id`.

## Objective

Add one harmless unit test file containing a single trivially true assertion,
proving the External Intelligence Automation daemon on M4, after the
2026-10-14 ChatGPT Team / GPT-5.6 transport change, can discover, validate, execute, verify, and publish one approved
Task Card unattended with `semantic_backend=open_swe` and
`worker_backend=open_swe`.

This card exists solely to exercise the live chain once:

daemon natural polling -> targeted remote-main refresh -> exact-main Task Card
authority validation -> open-swe semantic compilation -> open-swe worker
execution -> deterministic verification/closure -> exactly-once GitHub
publication -> stop at independent acceptance.

## Diagnosis scope

The semantic diagnosis covers only this card's required change, not the
end-to-end pipeline. The target test file is absent at the bound `main_sha`,
and its required content is fully specified below, so the change is a
fully specified additive change whose diagnosis is supported by the Task Card
and the absent target path. End-to-end daemon, worker, verification, and
publication behavior is what this canary run observes; the semantic stage
does not have to prove it in advance.

## Allowed files

- `tests/ops/test_external_intelligence_open_swe_canary_20261014.py`

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
python3 -m pytest -q tests/ops/test_external_intelligence_open_swe_canary_20261014.py
sh -c 'git diff --check "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA"'
sh -c 'test -z "$(git diff --name-status --diff-filter=D "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA")"'
```

## Worker binding

The worker is whatever the canonical planner seam binds for the configured
open-swe backend. This card creates no model-selection authority and pins no
provider or model.

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants
no approval, merge, integration, release, production, or autonomous follow-on
authority.
