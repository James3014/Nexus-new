# Task Card 00: EIA V10 Normal-Operation Canary R2

## Identity

- task_id: `eia-v10-normal-operation-20260821-r2`
- campaign_id: `external-intelligence-v10-normal-operation-20260821-r2`
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

## Supersession / replay-fence lineage

This card is a fresh execution identity for Issue #349's original harmless V10
normal-operation canary objective. It does not retry or overwrite the historical
`eia-v10-normal-operation-20260816` identity. That historical initial attempt
reached durable `TERMINAL_BLOCKED` after a semantic provider session was created,
so its replay fence remains immutable.

Dispatch-time main authority is not encoded as a mutable card-local SHA. The
runtime must bind this exact raw Git blob through Issue #349's fenced contract:
`main_sha` selects the canonical commit and `task_card_hash` is the SHA-256 of
this exact raw blob at that commit. The Issue `task_id` must equal this card's
`task_id`.

## Objective

Add one harmless unit test that asserts `True`, proving the External
Intelligence Automation (EIA) background daemon can discover, validate, execute,
verify, and publish one approved Task Card unattended from fresh canonical
`James3014/Nexus-new` main. This card exists solely to exercise the daemon
polling -> remote-main refresh -> exact-main Task Card authority validation ->
Sidecar A+B dispatch -> exact frozen V10 worker/model fixture -> deterministic
verification -> closure publication chain exactly once.

## Allowed files

- `tests/ops/test_external_intelligence_v10_normal_operation.py`

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
python3 -m pytest -q tests/ops/test_external_intelligence_v10_normal_operation.py
git diff --check
git diff --name-status --diff-filter=D
```

## Frozen V10 canary fixture

For this V10 baseline only, the execution path must attest provider `opencode`
and exact model `opencode-go/deepseek-v4-flash` with no silent fallback. This is
not standing EIA routing policy and creates no worker-selection authority;
CapabilityPlanner and Workforce Admission remain authoritative outside this
frozen canary fixture.

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card does
not grant approval, merge, integration, release, production, or autonomous
follow-on authority.

## Exit criteria

Exactly one completion publication is emitted with
`current_gate=PENDING_INDEPENDENT_ACCEPTANCE`; the execution is bound to the
canonical main selected by Issue #349's fresh `main_sha`; this card's raw blob
SHA-256 exactly equals Issue #349 `task_card_hash`; exactly one fresh semantic
execution occurs under the new task/unit identity; the canonical runtime checkout
remains clean and unchanged by worker execution; the daemon remains healthy;
and no manual execution substitute is used.
