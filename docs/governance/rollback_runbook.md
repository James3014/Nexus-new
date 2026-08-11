# Rollback Runbook

- Purpose: current operator procedure for governed integration rollback and self-hosted lifecycle closure
- Authority: current
- Owner: Nexus operators
- Status: active
- Evidence: self-hosted lifecycle implementation candidate `5975d17f90deabf3a26af1e1e9add93793f42da8`

## Self-hosted task lifecycle

Use one stable `task_id` for a single objective. A retry creates a new
`attempt_id`; it must not create a second Controller or a `v2`/`v3` task
identity. A serial task may have at most one active Target.

The governed MCP surface is:

```text
nexus_self_hosted_status
nexus_self_hosted_reconcile_tasks
nexus_self_hosted_cleanup
nexus_self_hosted_archive_state
nexus_self_hosted_approve_promotion
nexus_self_hosted_integrate_approved
nexus_self_hosted_dispose_candidate
nexus_self_hosted_cancel_task
```

Before Target cleanup, verify that the candidate commit, candidate tree,
candidate packet, verified receipt, and exact durable candidate ref all
resolve. Cleanup must fail closed for an active process, an unprotected
candidate, or dirty unique content. `RETAINED_FOR_REVIEW` is never
force-removed.

Approval binds all four values:

```text
candidate_commit_sha
candidate_tree_sha
candidate_state_hash
verified_receipt_hash
```

Integration is allowed only after those values are revalidated. The lifecycle
closure integration branch is:

```text
nexus/integration/self-hosted-lifecycle-closure
```

Protected main is never an integration target, and the integration operation
never pushes.

## External bootstrap recovery

Use this boundary only when independent evidence shows that the identity,
action-authorization, or state-transition contract of the controller,
lifecycle, Gateway, activation, or another authority needed to prove the
normal self-hosted mutation identity is itself defective, **and** current
evidence cannot bind a clean, trustworthy source/runtime/action identity
without circularly trusting that defect. An ordinary provider, model, quota,
test, timeout, or correctly blocking healthy lifecycle failure does not
qualify; it remains on the normal governed path.

For a qualifying bounded repair:

1. Stop retrying the untrustworthy self-hosted mutation path.
2. Freeze one exact known-clean repository base and its source evidence.
3. Create an external clean repair worktree from that exact base. Never copy a
   whole file or commit from a dirty canonical checkout.
4. Admit only the explicit evidence-bounded files and semantic delta.
5. Freeze one repair commit identity with exact parent, tree, and full diff.
6. Fail closed if the base, parent, tree, full diff, or source/runtime/action
   identity is missing, substituted, stale, or tampered.
7. Run affected positive, negative, tamper, retry/idempotency, and regression
   checks. A retry keeps the same `task_id` and uses fresh `attempt_id`,
   `action_id`, and `idempotency_key` values; it must not create a second
   Controller or a `v2`/`v3` task identity.
8. Obtain independent review of the frozen commit and its evidence by an
   authority distinct from the implementer.
9. Keep Candidate approval, integration, push, reload, activation, and cleanup as
   separate explicit authorities; repair completion performs none of them.
10. After separately authorized clean-source acceptance and activation,
   reacquire loaded source/runtime/action identity and verify affected live
   behavior, not process liveness alone.

Exit bootstrap recovery as soon as the repaired canonical authority can again
establish trustworthy current identity. Resume the normal governed path;
bootstrap recovery is not a permanent alternative lifecycle, Router, Planner,
approval path, integration path, or release node.

`CapabilityPlanner` remains the sole route and capability-selection authority;
`HybridRouteDecision` remains only its derived decision projection.

## Integration rollback

1. Record the integration branch original SHA.
2. Revalidate the approved binding and candidate ref.
3. Run governed integration and the post-integration verifier.
4. Mark `INTEGRATED` only when verification succeeds.
5. If integration or verification fails, restore only the integration branch
   to its recorded original SHA and persist `INTEGRATION_FAILED`.
6. Preserve the candidate commit, candidate ref, receipt, and failure evidence.
7. Do not modify protected main, delete refs, or push.
