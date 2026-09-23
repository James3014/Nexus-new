# Task Card 00 — Issue #973 governed one-shot Runtime Recovery consumer

```yaml
task_id: ISSUE-973-RUNTIME-RECOVERY-GOVERNED
attempt_id: ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R1
campaign_id: github-issue-973-runtime-recovery-governed-20260923
issue: 973
repository: James3014/Nexus-new
status: READY_AFTER_TRACKING
contract_kind: TRACKED_TASK_CARD
execution_lane: GOVERNED
auto_chain: false
worker_may_commit: true
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
commit_required: true
candidate_required: true
independent_acceptance_required: true
allow_deletions: false
maximum_touched_production_files: 6
maximum_touched_test_files: 2
claim_ceiling: SOURCE_CANDIDATE_AND_INDEPENDENT_ACCEPTANCE_ONLY_NO_RUNTIME_ACTIVATION
```

## Goal

Implement the #973 one-shot `RUNTIME_RECOVERY` authority consumer without creating a
second runtime manager, then close the two High defects found by independent review of the
prior non-governed Candidate.

The governed Candidate must make one exact Owner-authorized recovery effect possible and
fail closed for stale, revoked, replayed, widened, tampered, or outcome-unknown authority.
It must reuse the existing Gateway durable recovery mechanism for physical restart,
rollback, durable effect ledger, reconciliation, authenticated identity/health postflight,
and effect idempotency.

## Source lineage and immutable basis

- GitHub Issue #973 body SHA-256:
  `4af2812fb7c84aec5d73ee74d9e74a4881a1d9a949b2e59602b6d211d6048b2f`.
- Owner governed decision SHA-256:
  `5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5`.
- Task-card bootstrap standing grant receipt hash:
  `00d766ce52dfac3a85a6fdc8d6ac9b222f6aee2c4432424b7639c0b00d02487d`.
- Bound planning base:
  `2619f9f9121448b81bed8fe84556186892849e76` /
  tree `76bdd05e94e2a1ba01f5364605f2e42ea922822a`.
- Historical direct Candidate donor only:
  `fbf6c00c7f1912846ccab843bdd9d534b9f19c19` /
  tree `714f6d776a237364d04adadf5d41d7004ffd4ac6`.

The prior direct Candidate is not an acceptance receipt and must not be merged. It may be
used only as a patch/evidence donor after this exact Card is physically tracked on `main`.

## Required behavior

1. Define a separate Owner runtime-recovery authority payload/envelope that binds:
   - canonical break-glass authority home;
   - implementation Issue #973;
   - exact recovery/attempt identity;
   - `RUNTIME_RECOVERY` only;
   - fixed action `GATEWAY_DURABLE_RECOVERY`;
   - fixed service `com.nexus.mcp.gateway.direct`;
   - exact `GatewayRecoveryRequest` identity/hash/idempotency fence;
   - exact desired/predecessor manifest identity/hashes;
   - bounded issuance/expiry window;
   - claim ceiling `runtime_recovery_only`.
2. Before the durable effect-commit boundary, the consumer must re-read current Owner
   revocation evidence and evaluate expiry using a **fresh clock obtained immediately before
   durable `DISPATCHED`**. A timestamp captured before remote/revocation readback is not
   sufficient.
3. `DISPATCHED` is the one-shot effect-commit boundary. After it is durable, timeout,
   disconnect, crash, lost acknowledgement, later expiry, or later revocation may only
   reconcile the same request ID/hash/fence; they must never mint or send a replacement
   effect.
4. Physical activation/restart, rollback, durable manager ledger, authenticated postflight,
   and effect idempotency remain owned by existing `scripts/ops/mcp_gateway_durable.py` and
   `nexus/contracts/gateway_deployment.py`. Do not duplicate or modify that owner unless an
   independently proven defect requires an explicit card delta first.
5. Outer PREPARED/DISPATCHED/TERMINAL evidence must be semantically re-verifiable from exact
   Owner authority + exact request/outcome, not merely self-hashed. Same-UID rewrite plus
   recomputed self-hash of phase/status/effect/evidence/claim fields must be rejected.
6. Terminal states may include `CONSUMED`, `ROLLED_BACK`, or exact fail-closed terminal forms
   defined by the existing manager outcome. Terminal authority denies replay.
7. Outer durable receipts must not persist raw secrets, tokens, environment, raw host
   observations, arbitrary paths, arbitrary service selectors, or arbitrary command input.
8. CLI surface may accept only the exact Owner authority subject and exact Gateway request;
   it must not expose arbitrary service/path/action/executable/shell selectors.

## Mandatory negative controls

Prove at minimum:

- expired grant immediately before effect commit => no executor call;
- Owner revocation appearing before effect commit => no executor call;
- wrong request ID/hash/fence/manifests => no executor call;
- wrong/widened effect/action/service/claim ceiling => validation failure;
- terminal replay => no second effect;
- lost acknowledgement after possible effect => only same-request reconciliation;
- later expiry/revocation after durable `DISPATCHED` cannot create a replacement effect;
- rollback becomes exact terminal evidence and denies replay;
- PREPARED, DISPATCHED, and TERMINAL chain tamper fails closed;
- self-rehashed DISPATCH semantic tamper fails closed;
- self-rehashed TERMINAL tamper of `status`, `phase`, `effect_started`, evidence hash,
  observation hash, request binding, or claim ceiling fails closed;
- malformed/fake Owner comment or payload-hash mismatch fails closed;
- terminal outer receipt contains hashes/typed identities only, not raw host observation or
  credential/environment material.

## Allowed files

Only:

- `nexus/contracts/break_glass_recovery.py`
- `nexus/orchestrator/break_glass_recovery.py`
- `scripts/ops/break_glass_recovery.py`
- `tests/contracts/test_break_glass_recovery_contract.py`
- `tests/nexus/orchestrator/test_break_glass_recovery.py`
- `docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md`
- `docs/governance/rollback_runbook.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`

Any additional source/test/doc path requires an explicit contract delta before mutation.
No deletions.

## Forbidden scope

- no modification of `scripts/ops/mcp_gateway_durable.py`;
- no modification of `nexus/contracts/gateway_deployment.py`;
- no second runtime manager, restart owner, rollback owner, planner, verifier, receipt owner,
  or Completion truth owner;
- no live runtime activation under this card;
- no launchd/service/restart action during source implementation or verification;
- no source repair or emergency integration authority reuse;
- no arbitrary shell/command/path/service selector;
- no PR approval, protected merge, release, production, or public-success authority in worker
  scope;
- no secrets, keys, tokens, environment dumps, or raw host observations in committed
  evidence.

## Start-state proof and classification

- Canonical main at card compilation:
  `2619f9f9121448b81bed8fe84556186892849e76`.
- Prior direct Candidate exists but is not authorized implementation lineage for this card.
- Independent exact-Candidate review found two source-grounded High blockers:
  `STALE_EFFECT_COMMIT_TIME` and `SELF_REHASHED_TERMINAL_EVIDENCE_FORGERY`.
- **Start classification:** `DEFECT_REPRODUCED_BY_INDEPENDENT_REVIEW`.
- The governed implementation must start from freshly rebound canonical main **after this
  card is tracked on main**, not by continuing the old direct branch.

## Mandatory source audit

Before editing, re-read:

- root `AGENTS.md` and `docs/agents/TASK_EXECUTION_CONTRACT.md`;
- this exact Card/INDEX and their hashes;
- Issue #973 current body/comments;
- `nexus/contracts/break_glass_recovery.py`;
- `nexus/orchestrator/break_glass_recovery.py`;
- `scripts/ops/break_glass_recovery.py`;
- donor recovery seams in `scripts/ops/mcp_gateway_durable.py` and
  `nexus/contracts/gateway_deployment.py`;
- focused break-glass and Gateway recovery tests;
- open PR overlap, including legacy PR #1062.

## Implementation constraints

- Use the smallest end-to-end tracer bullet that satisfies Issue #973.
- The prior direct Candidate patch may be replayed/cherry-picked only **after** this card is
  tracked on main and only if the resulting physical diff remains inside this card.
- Do not widen the trusted Gateway manager contract to make outer break-glass code easier.
- Preserve backwards compatibility for existing break-glass source-repair and emergency-
  integration behavior.
- `OUTCOME_UNKNOWN != retry permission`; reconcile exact external effect identity.
- Tests are witnesses, not authority. A green subset cannot override a scope or authority
  violation.

## Verification commands

At minimum, from the clean governed implementation worktree:

```sh
uv sync --all-groups --all-extras
uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py
uv run pytest -q tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed
uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py
uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py
uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py
git diff --check
```

Run the narrowest additional affected tests required by actual imports. If a donor-manager
suite is host-bound on the current Mac, preserve the exact failure signature and do not
rewrite donor source/tests merely to make that host pass.

## Candidate and independent acceptance

- implementation must occur from a clean branch/worktree created from current canonical main
  after this Card is tracked;
- Candidate commit is required;
- complete changed-path set and exact base/head diff must be captured;
- all required verifiers must pass or have an explicitly bounded pre-existing host-only
  failure classification;
- a fresh reviewer distinct from the implementer must inspect the **new exact governed
  Candidate**, complete diff, donor ownership boundaries, crash/replay semantics, evidence
  authenticity, and test-oracle strength;
- prior review of `fbf6c00c...` does not accept the new Candidate;
- implementer cannot self-accept, approve, merge, release, activate runtime, or make
  production/public claims.

## Exit conditions

**PASS** requires:

1. exact governed Candidate independently returns no blocking/material defect;
2. required branch-protection/trusted checks are green on the exact head;
3. no deletion or out-of-card path;
4. accepted Candidate is integrated through the repository's governed completion path;
5. post-merge source/readback proves exact integrated tree and focused source verification.

**BLOCK** on any authority widening, stale/revoked pre-DISPATCH acceptance, same-effect blind
resend, self-rehashed semantic evidence forgery, raw secret/host-observation persistence,
donor-manager ownership duplication, material main drift, failed required check, or
independent-review blocker.

Runtime activation is outside this Task Card and requires a separate exact Owner runtime
authority after source integration.

`AUTO_CHAIN=false`.
