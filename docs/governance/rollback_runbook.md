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

## Integration rollback

1. Record the integration branch original SHA.
2. Revalidate the approved binding and candidate ref.
3. Run governed integration and the post-integration verifier.
4. Mark `INTEGRATED` only when verification succeeds.
5. If integration or verification fails, restore only the integration branch
   to its recorded original SHA and persist `INTEGRATION_FAILED`.
6. Preserve the candidate commit, candidate ref, receipt, and failure evidence.
7. Do not modify protected main, delete refs, or push.
