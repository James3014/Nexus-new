# TASK-526-HOST-1 — Gateway stable artifact, rebind, and local authenticated canary

```yaml
task_id: TASK-526-HOST-1
issue: 526
repository: James3014/Nexus-new
status: BLOCKED
blocked_by: TASK-526-B-AUTHORITY
execution_realm: LOCAL_HOST_BOUND_EXTERNAL_BOOTSTRAP
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: NEXUS_GATEWAY_REBIND_LOCAL_CANARY_VERIFIED_ONLY
owner_activation_id: OWNER_ISSUE526_CONTINUE_20260823
owner_activation_sha256: f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322
```

## Authority boundary

This Card authorizes one exact local Gateway host-effect sequence only after
`TASK-526-B-AUTHORITY` is merged and independently accepted. It is the
separate activation authority required by the merged Slice A Card. It grants no
source implementation, GitHub merge, DevSpace mutation, release, production,
or auto-follow-main authority.

Normal self-hosted mutation identity is circular for this repair because the
loaded Gateway/controller identity is the authority being rebound. Therefore
this one activation uses the bounded external bootstrap boundary in
`docs/governance/rollback_runbook.md`; it creates no second Controller and
must exit immediately after the repaired Gateway reacquires trustworthy live
identity.

Activation is bound to Owner `owner-james`, source thread
`01a02a17-691c-7a20-ad0f-9166456416dc`, exact Owner message
`都同意，繼續` (SHA-256 above), and primary coordinator
`coordinator-codex`. Only that coordinator may issue the canonical
host-authority receipt after the authority correction is independently
accepted and merged. The implementation worker cannot create, approve, revoke,
or use that receipt as its own authority.

## Frozen source and profiles

- source-provenance base merge:
  `ac4a9ab1e0180170ca062cdc81f2142bca8bd80f`
- source-provenance base tree:
  `db329f4931b55b74f1e1f9fe61f7edf4ca8422bc`
- manager source path: `scripts/ops/mcp_gateway_durable.py`
- authority-correction merge SHA/tree, final manager SHA-256, independent
  acceptance receipt hash, and current-main ancestry are
  `REQUIRED_AT_ACTIVATION`: the coordinator must bind their exact post-merge
  values in the host-authority receipt. The source base above is not sufficient
  activation identity and the pre-correction manager must never be installed.
- rollback/current root:
  `/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe`
- rollback/current HEAD/tree:
  `67521fe91e990f4e140642984c743dd50a408e84` /
  `f6d6c2bf0912ff4a63d3c10a089910f95eab3c12`
- desired Gateway root:
  `/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3`
- desired HEAD/tree:
  `7ad264e1c12a2b4d3896b4cdeec68688acf034f7` /
  `b9057f8ef736fb6d3cd30da983f33f5f61fb86e9`
- fixed Gateway entrypoint SHA-256:
  `8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1`
- fixed interpreter link:
  `/Users/jameschen/Workspace/Nexus-new/.venv/bin/python`
- fixed interpreter target SHA-256:
  `c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78`
- fixed service: `gui/501/com.nexus.mcp.gateway.direct`
- fixed endpoint: `http://127.0.0.1:8766`

Every value is dispatch-preparation evidence and must be physically reread
immediately before the first effect. Drift blocks; it never selects a newer
main or another worktree automatically.

## Exact host mutation targets

Only these machine-local targets may change:

- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/manager.py`
- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/request.json`
- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/host-authority.json`
- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/evidence.json`
- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/ledger.jsonl`
- `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/ledger.lock`
- `/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist`
- `gui/501/com.nexus.mcp.gateway.direct`

No repository file, DevSpace file/service, other LaunchAgent, route/Planner,
Workforce policy, external platform, or unrelated runtime state may change.

The state directory and files must be owned by numeric UID `501`: directory
mode `0700`; `host-authority.json`, `request.json`, `evidence.json`,
`ledger.jsonl`, and `ledger.lock` mode `0600`; installed `manager.py` mode
`0700`. Each JSON store is capped at 64 KiB, duplicate keys and symlinks are
rejected, and unsafe/writable ancestry blocks before effects.

## Canonical host authority receipt

After `TASK-526-B-AUTHORITY` is accepted and merged, coordinator
`coordinator-codex` issues exactly one owner-only
`nexus.gateway.host_effect_authority.v1` receipt at the fixed
`host-authority.json` path. Required top-level fields are:

- `schema`, `receipt_version`, `receipt_id`, and `receipt_hash`;
- `issuer_id=owner-james`, `coordinator_id=coordinator-codex`, and
  `authorized_actor_id=coordinator-codex`;
- `owner_activation_id`, `owner_activation_sha256`, and source thread;
- standing-grant ID
  `OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW` and receipt
  SHA-256
  `3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5`;
- exact authority-correction merge SHA/tree, independent acceptance receipt
  hash, final manager SHA-256, and current main SHA;
- host Card ID/path/SHA-256;
- repository, operation, effect class, fixed label/plist/endpoint, current and
  desired profile hashes, request ID, and idempotency fence;
- `issued_at`, `expires_at`, `revocation_state=NOT_REVOKED`,
  `revoked_at=null`, and `revocation_reason=null`.

Owner `owner-james` is the sole revocation authority. Revocation is an atomic
replacement of this same fixed canonical store with
`revocation_state=REVOKED`; the manager rereads the latest store immediately
before every first effect. No separate caller-selected revocation path exists.

## Pre-effect reconciliation

The current `/health` reports `pending_actions=1`. Formal authenticated
`nexus_task_reconcile` and `nexus_task_status` reacquired the exact task:

- task: `issue517-worktree-agy-probe-v1`
- action: `action-8f2212775d5542239337b1c29aec213f`
- attempt: `attempt-6dde87e7ee614c86a5b2d85389169d6a`
- status/blocker: `FAILED` / `ASSIST_PROVIDER_PROCESS_LOST`
- process cleanup: `true`
- uncertain mutation: `false`
- filesystem delta: empty
- retry was not issued

This failed attention item is durable pending state, not an action to complete.
The host evidence receipt must represent it with disposition `reconciled` and
must never claim the task succeeded or drained.

## Required sequence

1. Reread exact Git, source bytes, target cleanliness, plist bytes/hash,
   interpreter link/target/hash/owner/mode, service/PID/listener, authenticated
   health identity, stable artifact predecessor, and durable quiescence.
2. Verify the exact authority-correction merge/main/tree and independent
   acceptance receipt, then have only `coordinator-codex` issue the canonical
   host-authority receipt above. Create request/evidence stores from this Card,
   hash/read all stores back, and keep receipt issuance separate from the host
   effect operator.
3. Run Gateway preflight. Source-only, stale, revoked, substituted, unbound, or
   self-issued authority must fail before any filesystem/process effect.
4. Acquire the inter-process ledger lock and install the stable manager as a
   separate exact operation. The absent predecessor is explicit; normal reload
   never installs the artifact.
5. Persist the exact request/evidence stores, then execute only the fixed
   Gateway reload operation through the installed manager.
6. Require authenticated `/health`, MCP `initialize`, and `tools/list` proof of
   a new server instance serving the desired root/HEAD/tree, exact manifest,
   full schema, permission/action/task/lifecycle identity, and client binding.
7. Persist the legal ledger chain through `VERIFIED` only after postflight.
8. Exercise the exact rollback verifier without manufacturing success. A
   destructive rollback drill is allowed only if a canary failure occurs or a
   separate explicit test mode proves exact predecessor restoration without a
   second service.
9. Reread launchd, listener, health, stores, ledger, and Issue state. Record no
   DevSpace effects and keep Issue #526 open until the #398-serialized
   ChatGPT-facing action canary is separately complete.

## Negative controls

- Source Candidate receipt alone cannot preflight/install/reload/rollback.
- Wrong source merge/tree, Card hash, operation/effect, request/fence, service,
  plist, profile, endpoint, issuer/coordinator, validity, or revocation blocks
  before effects.
- Existing `STARTED` or `UNCERTAIN_EFFECT` physically reconciles the same
  request; it never launches a second Gateway.
- Any postflight mismatch persists uncertainty and uses only the exact captured
  predecessor for rollback.
- No result is a production, release, DevSpace, or general auto-follow-main
  claim.
- Host `status`, if used, is a separate `STATUS` receipt and reads only the
  fixed Gateway service. Legacy dual-service `manage("status")` is not an
  authority surface and cannot be reached by the host CLI.

## Verifiers and exit

- exact stable artifact/source/store hashes and safe modes;
- fixed-label launchctl and single-listener evidence;
- authenticated health + initialize + tools/list receipt;
- complete ledger/CAS/state chain and rollback evidence;
- zero DevSpace/unrelated effect audit;
- independent acceptance distinct from the effect operator.

The dependency unlock is not a status label: it requires the exact merged
authority-correction main SHA/tree, exact independent acceptance receipt hash,
and a current valid canonical host-authority receipt binding those values.

`PASS` means only `NEXUS_GATEWAY_REBIND_LOCAL_CANARY_VERIFIED_ONLY`.
`AUTO_CHAIN=false`; stop before #398-serialized Slice B/ChatGPT-facing work.
