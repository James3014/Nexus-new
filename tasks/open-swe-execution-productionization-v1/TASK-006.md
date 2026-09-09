# TASK-006 — Resident Open SWE automation activation for five repositories

task_id: `TASK-006`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `COMPLETED_AT_BOUNDED_CLAIM_CEILING`
- **Authority:** explicit current Owner request plus the r28 closeout evidence; Issues #895 and #906 remain historical bounded repair context. Issue #906 / PR #908 was rejected and closed unmerged; no recovery from that proposal entered Nexus-new main.
- **Auto-chain:** `false`
- **Maximum claim:** `RESIDENT_OPEN_SWE_AUTOMATION_READY_FOR_FIVE_MOUNTED_REPOSITORIES` (r28 bounded ceiling)
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

## r23 effect-verified Candidate recovery amendment (historical, rejected)

Issue #906 / PR #908 was rejected and closed unmerged. No recovery from that proposal entered Nexus-new main. The following records the historical r23 contract and its fail-closed boundary; the accepted r28 closeout is bound to the later runtime composite/reconciliation fixes and does not retroactively accept #906 or PR #908.

Issue #906 permitted one narrow recovery when an Open SWE worker has already
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

The inspector is limited to the configured local runtime state root and the
exact operation. It may read only the declared recovery-operation record and a
bounded effect-file set, using the frozen local schemas without importing the
runtime package. The root, parent directories, records, and physical target
must be owner-controlled, non-symlink, and not group/world writable. Unbounded
enumeration, malformed JSON, unknown schema, or more than one matching effect
fails closed.

Before committing, fanout must CAS an absorbing recovery intent bound to the
attempt, operation, effect, expected base, planned Candidate tree material, and
receipt identity. Replay at pre-commit, post-commit/pre-receipt, or
post-receipt/pre-attempt-complete cuts must converge to the same Candidate and
receipt, or fail closed. None of these cuts may issue another Web request,
repeat the physical write, or create a second commit.

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
8. After the final generation first passes, run an intentional rollback drill: restore the immediately prior known-good config/plist/runtime generation, prove a new rollback PID/run reaches `READY`, restore the final generation, and repeat the three-poll, 120-second readiness gate.
9. On any unexpected activation, readiness, rollback, or restore failure, remain on the last proven known-good generation and stop; never redeploy the generation that just failed.

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

- **PASS:** r28 source/runtime/config/PID-bound evidence, five-mount witness, rollback/restored-final evidence, and one harmless unattended canary reaches the recorded independently accepted Candidate boundary.
- **BLOCK:** any identity drift, missing canonical clone, stale readiness, Web hard block, unknown operation, verifier failure, or rollback uncertainty.

The r28 closeout is documentation-only and does not claim source merge, independent acceptance, release, production readiness, or mutation readiness across all five repositories.


## r28 bounded completion record

TASK-006 closes at its existing bounded claim ceiling against the following exact evidence:

- Nexus-new base: `a59b8ab23a91ae4470300a34b4691567255c12af`
- Runtime main: `3eb673bfcfd874043a70743e34761784fda39c10`
- r28 operation: `96b83c02de43ff8e6bc37d49e0efabd3f113ac60135ea214c367094b24806574`
- Durable effect: `ef0802c64e2a8e8f8a65ccb696adf1b0d9d50b21a06348e10d931a038d88af68`
- Unit Candidate: `2d41308d27999f210627981a933f8f0da95e54f0`
- Task Candidate: `c5979ffbc664e019f6790bc5f6c84210749fa43c`
- Candidate tree: `a85cd07d4dc2d17f7551869565fcbc2fcf6512f3`
- Task Card hash: `d39a297583ebf37cdfbd0efa09a8c16f3ecf11ec7b9ced8a43dcc07d18d31fb1`
- Whole-task verification: `512530748d61ea0537f5019956bbf07bbbec33a9e724a0790bdeb15cd47d3c6d` (`PASS`)
- Acceptance packet: `1b089e62d2077fbc18e96e37952128155c63cec4d07d86b798075a9fef555b93`
- Worker receipt: `b893c704f2b8e2632d94c203f44a25a87f32dc9e9758ab5f9ac2d1ec0fb4d2b1`
- Five-mount receipt SHA: `89d36c80399c15a4fe306c28318f4108d4b64cd90a1c94c643e8892bf4576f53`
- Final rollback/restore receipt SHA: `1b7ce771a8b4aa14e94045a36b0a9aeeabcd9ed09b4a986ce1d87b1326907888`
- Closure capsule: `ec02d8d07d681b88751ba20b7e1fbb8afdf1e103882554926fd5a4d6511a7694`
- Resident final READY run: `0eb9a96de9f64454b21362a141a7d41a`

The original acceptance packet and closure capsule record `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` with gate `PENDING_INDEPENDENT_ACCEPTANCE` as historical artifact state; controller receipt `9638ef72801a31ca84560b8b7d3d99bd512925b593f7b535b993b762b5860cf6` records independent acceptance. This closeout preserves r21-r27 historical fail-closed evidence, `AUTO_CHAIN=false`, and all no-approval, no-merge, no-push, no-release, and no-production boundaries. It does not claim that all five repositories are mutation-ready; each future job still requires its own Task Card, exact Issue contract, verifiers, and independent Candidate acceptance.
