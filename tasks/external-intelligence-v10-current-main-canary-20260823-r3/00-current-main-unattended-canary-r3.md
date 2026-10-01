# Task Card 00: EIA V10 Current-Main Unattended Canary R3

## Identity

- task_id: `eia-v10-current-main-canary-20260823-r3`
- campaign_id: `external-intelligence-v10-current-main-canary-20260823-r3`
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

This is a fresh execution identity for Issue #530. It does not retry, overwrite,
or reinterpret Issue #349's historical `eia-v10-normal-operation-20260821-r2`
execution. The new unit identity must also be fresh so the fanout receipt store
cannot reuse an older `task_id + unit_id` key.

Dispatch-time main authority is not encoded as a mutable card-local SHA. The
runtime must bind this exact raw Git blob through Issue #530's fenced contract:
`main_sha` selects the canonical commit and `task_card_hash` is the SHA-256 of
this exact raw blob at that commit. Issue `task_id` must equal this card's
`task_id`.

## Objective

Add one harmless unit test file containing a single trivially true assertion,
proving the current-main External Intelligence Automation background daemon can
discover, validate, execute, verify, and publish one approved Task Card
unattended from fresh canonical `James3014/Nexus-new` main.

This card exists solely to exercise the complete live chain once:

daemon natural polling -> targeted remote-main refresh -> exact-main Task Card
authority validation -> Sidecar semantic compilation -> fresh bounded OpenCode
worker execution -> deterministic verification/closure -> exactly-once GitHub
publication -> stop at independent acceptance.

## Allowed files

- `tests/ops/test_external_intelligence_v10_current_main_canary.py`

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
python3 -m pytest -q tests/ops/test_external_intelligence_v10_current_main_canary.py
git diff --check
git diff --name-status --diff-filter=D
```

## Frozen V10 canary worker fixture

For this verification baseline only, the execution path must attest provider
`opencode` and exact model `opencode-go/deepseek-v4-flash` with no silent
fallback. This is not standing EIA routing policy and creates no model-selection
authority; it preserves comparability with the completed #349 V10 baseline.

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants
no approval, merge, integration, release, production, or autonomous follow-on
authority.

## Exit criteria

Exactly one completion publication is emitted for Issue #530 with
`current_gate=PENDING_INDEPENDENT_ACCEPTANCE`; execution is bound to the
canonical main selected by Issue #530's fresh `main_sha`; this card's raw blob
SHA-256 exactly equals Issue #530 `task_card_hash`; exactly one fresh Sidecar and
worker execution occurs under the new task/unit identity; the Candidate changes
only `tests/ops/test_external_intelligence_v10_current_main_canary.py`; unit and
whole-task verifiers pass; the dedicated EIA runtime checkout remains on the
same exact current-main HEAD, clean and unchanged by worker execution; and the
daemon remains public `READY` after the run.
