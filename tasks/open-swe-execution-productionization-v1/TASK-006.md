# TASK-006 — Resident Open SWE automation activation for five repositories

task_id: `TASK-006`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `ACTIVE`
- **Authority:** explicit current Owner request plus Ready GitHub Issues #850, #895, and #906; #895 is limited to the r21 same-operation reconciliation amendment and #906 to the r23 effect-verified Candidate recovery below
- **Auto-chain:** `false`
- **Maximum claim:** `RESIDENT_OPEN_SWE_AUTOMATION_READY_FOR_FIVE_MOUNTED_REPOSITORIES`
- **Task type:** `INTEGRATION_ACTIVATION`
- **Candidate required:** `true` for repository source changes
- **Worker may approve/merge/release:** `false`

## Goal

Integrate the accepted Nexus consumer correction into current `James3014/Nexus-new` main, install a durable standalone `nexus-open-swe-runtime`, and activate `com.nexus.external-intelligence` so it autonomously discovers eligible GitHub Issues for these exact mounted repositories:

1. `James3014/Nexus-new`
2. `James3014/devspace`
3. `James3014/nexus-core`
4. `James3014/nexus-learning`
5. `James3014/nexus-open-swe-runtime`

## Bound transport

- provider: `opencli_chatgpt`
- model: `balanced` ChatGPT UI intelligence level, not a fixed model slug
- site session: `ephemeral`
- OpenCLI: `1.8.7`
- Browser Bridge: `1.0.24`
- per-call timeout: `180`
- semantic operation timeout: `1200`
- worker operation timeout: `2400`
- window: foreground
- runtime state: existing External Intelligence state root

`persistent` and `very-high` from the earlier TASK-005 qualification contract are not activation defaults. Actual bounded Web evidence selected `ephemeral` and `balanced`; this change is bound to Owner Issue #850 and preserves TASK-005 as historical hardening context.

The earlier `600/1200` operation budgets were superseded after resident canary
revision r2 crossed model selection, created a real ChatGPT conversation, and
then reached the 600-second semantic deadline without a terminal result. That
attempt remains `OUTCOME_UNKNOWN`, `retry_safe=false`, and was not resent.

## Repository source scope

- `nexus/services/external_intelligence_automation.py`
- `nexus/services/external_intelligence_fanout.py`
- `nexus/services/open_swe_external_intelligence.py`
- `tests/services/test_external_intelligence_automation.py`
- `tests/services/test_external_intelligence_fanout.py`
- `tests/services/test_open_swe_worker_transport.py`
- `docs/ops/OPEN_SWE_STANDALONE_CONSUMER.md`
- `scripts/ops/configs/external_intelligence_open_swe_activation_v1.json`
- `scripts/ops/external_intelligence_service.py`
- `tests/services/test_external_intelligence_service.py`
- `tasks/open-swe-execution-productionization-v1/INDEX.md`
- `tasks/open-swe-execution-productionization-v1/TASK-005.md`
- `tasks/open-swe-execution-productionization-v1/TASK-006.md`
- `tasks/open-swe-resident-five-repo-canary-20260908/INDEX.md`
- `tasks/open-swe-resident-five-repo-canary-20260908/00-canary.md`

No other repository source file may change. No deletion is allowed.

## r21 same-operation reconciliation amendment

Issue #895 extends TASK-006 only far enough to preserve the existing fanout
operation after a recoverable unknown outcome. When every admitted unit reports
exactly `FANOUT_RECONCILIATION_REQUIRED`, automation state must remain
`RECONCILIATION_REQUIRED` with `prior_state=FANOUT_DISPATCHING`, the exact
intelligence effect, canonical worker binding, workspace, attempt, and operation
identity. A later resident poll must enter fanout reconciliation without a new
workspace, attempt, worker dispatch, or operation ID.

The already-observed r21 compatibility path may recover its legacy
`BLOCKED/FANOUT_INCOMPLETE` automation projection only when the current
Issue/main/Task Card identity is unchanged and every current unit has an exact
matching `OUTCOME_UNKNOWN` or `DISPATCHING` fanout attempt whose
`unit_identity_sha256`, workspace, and base match the reconstructed unit. The
canonical worker binding and intelligence effect must be recomputed from the
current authoritative Issue, Task Card, Planner/admission and source inputs;
FanoutStore identity and the existing runtime operation identity remain
mandatory. Missing, malformed, mixed, terminal, or identity-drifted state
remains fail closed. This amendment does not weaken truly terminal `BLOCKED`
reuse and does not authorize hand edits to runtime or automation state.

## r23 effect-verified Candidate recovery amendment

Issue #906 permits one narrow recovery when an Open SWE worker has already
closed exactly one authorized durable mutation but its post-effect terminal Web
turn remains outcome-unknown. The fanout controller may create only a
`CANDIDATE_READY_FOR_VERIFICATION` receipt when the existing attempt, runtime
recovery identity, operation, workspace, provider/model, worker identity,
allowed path, effect turn/call/arguments, physical postimage, expected base,
and exact one-file/no-deletion diff all match. The effect must be the only
effect for the operation and already be `RESULT`; `INTENT`, multiple effects,
another changed path, third-state bytes, stale identity, or an unexecuted
mutation stays `RECONCILIATION_REQUIRED`.

This recovery does not synthesize a model completion or accept the Candidate.
It emits an explicit host-derived `EFFECT_RECOVERED_PENDING_VERIFICATION`
receipt, after which the existing closure must execute the Issue-declared unit
and whole verifiers. Only verifier success may publish the Candidate. The
absorbing attempt/Candidate receipt prevents delayed provider output or later
polls from reopening the operation, repeating the physical effect, sending a
new Web turn, or creating a second commit.

## Deployment-owned paths

- `/Users/jameschen/.config/nexus-external-intelligence/config.json`
- `/Users/jameschen/Library/LaunchAgents/com.nexus.external-intelligence.plist`
- `/Users/jameschen/.local/share/nexus-open-swe-runtime/`
- `/Users/jameschen/Workspace/nexus-automation-repos/`

These are deployment state, not Git Candidate files. Back up exact prior bytes before replacement and retain a rollback receipt.

## Required behavior

1. The daemon SHALL poll the five configured repository IDs every 60 seconds for open Issues labeled `nexus:external-intelligence`.
2. Each repository ID SHALL map one-to-one to a clean dedicated Git checkout/worktree whose `origin` normalizes to the same `owner/repo`.
3. Both semantic and worker backends SHALL be `open_swe`; no silent OpenCode, Gemini API, or direct OpenCLI semantic fallback is allowed.
4. The standalone runtime SHALL be installed in a durable isolated virtual environment and SHALL pass the identity handshake with an exact module SHA-256 bound into host configuration.
5. Open SWE SHALL invoke the installed OpenCLI executable with explicit profile, `ephemeral` session, foreground window, and bounded timeouts.
6. Eligible Issue execution SHALL require one fenced machine contract with exact main SHA, Task Card reference/hash, mutation paths, unit verifiers, whole verifiers, and `pipeline_mode=FULL_PIPELINE`.
7. The daemon SHALL create isolated fanout/closure worktrees, preserve canonical checkouts, and stop at a verified Candidate pending independent acceptance.
8. Timeout, disconnect, locked host, login/challenge/quota, repository mismatch, runtime/config/adapter drift, or stale readiness SHALL fail closed without blind redispatch.

## Activation sequence

1. Integrate and independently accept the exact repository Candidate against fresh main.
2. Build/install current standalone runtime main and bind its identity/module hash.
3. Create or refresh five clean automation worktrees at their current remote main revisions.
4. Materialize host configuration with exact absolute paths and back it up.
5. Stop the old LaunchAgent once, confirm unload, install from the clean deployment checkout, then bootstrap once.
6. Require a new receipt bound to the new PID, source hash, config hash, runtime identity, and at least three consecutive successful 60-second polls spanning at least 120 seconds with no error.
7. Run one harmless unattended Issue canary under an existing repository-local Task Card; reconcile the same operation and verify Candidate evidence.
8. If any activation gate fails, restore the immediately prior known-good config/plist/runtime generation, prove a new rollback PID/run reaches `READY`, then restore the final generation and repeat the three-poll, 120-second readiness gate.

## Verification

```text
python -m pytest -q tests/services/test_external_intelligence_automation.py tests/services/test_external_intelligence_fanout.py tests/services/test_external_intelligence_service.py tests/services/test_open_swe_external_intelligence.py tests/services/test_open_swe_worker_transport.py
ruff check nexus/services/external_intelligence_automation.py scripts/ops/external_intelligence_service.py tests/services/test_external_intelligence_automation.py tests/services/test_external_intelligence_service.py
git diff --check
nexus-open-swe-runtime --identity
opencli doctor
python -m scripts.ops.external_intelligence_service status --config <host-config>
```

Additionally verify all five `origin` identities and fetched main SHAs, config and source hashes, LaunchAgent PID/argv, fresh heartbeat, and the unattended canary's semantic/worker/verifier/Candidate/reconcile receipts.

## Stop and authority boundary

- Repository source integration requires normal PR/Candidate acceptance and protected merge gates.
- Host activation is authorized by the current Owner request only for the exact five repositories and paths above.
- An Open SWE worker cannot approve or merge its Candidate, change routing/Workforce policy, release, or make a public production claim.
- Mount readiness does not authorize arbitrary repository mutation. Each autonomous Issue still requires its own Git-tracked Task Card and exact Issue contract.
- The Issue #850 contract itself SHALL NOT carry the workload label `nexus:external-intelligence`.

## Exit

- **PASS:** exact source Candidate merged; durable runtime identity verified; five repositories mounted; new source/config/PID-bound daemon readiness proven; one harmless unattended canary reaches verified Candidate and same-operation reconciliation without resend.
- **BLOCK:** any identity drift, missing canonical clone, stale readiness, Web hard block, unknown operation, verifier failure, or rollback uncertainty.
