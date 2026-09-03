# G20-GATEWAY-INERT-GITLINK-RECOVERY

```yaml
task_id: G20-GATEWAY-INERT-GITLINK-RECOVERY
status: ACTIVE
authority: OWNER_CURRENT_INSTRUCTION
owner_instruction: "目標設好，繼續完成"
base_commit: 8f46b3d265a561af05d61d97708c3b107242f29b
base_tree: 6092c60f523697d2d25be6279761264934b8b190
execution_lane: GOVERNED
auto_chain: false
```

## Objective

Repair the #526 durable Gateway recovery source-staging incompatibility with the current Nexus repository, whose exact accepted/desired/fresh-main trees contain pre-existing Gitlink entries without a tracked `.gitmodules` file. Preserve the original security goal: recovery must never fetch, initialize, execute, or trust Gitlink/submodule contents.

## Allowed files

- `scripts/ops/mcp_gateway_durable.py`
- `tests/ops/test_mcp_gateway_durable.py`
- `tasks/g20-learning-runtime-closure-20260903/INDEX.md`
- `tasks/g20-learning-runtime-closure-20260903/02-gateway-inert-gitlink-recovery.md`

## Required behavior

1. Gitlink entries are accepted only as inert superproject tree pointers when the commit has no tracked `.gitmodules` metadata.
2. Bundle and deployment identity remain bound to the exact full superproject commit/tree and existing content-addressed manifests.
3. Recovery must not recurse into or fetch Gitlink targets.
4. Every materialized Gitlink path must remain an empty, non-symlink directory with no nested `.git` state; otherwise fail closed before host effect.
5. A commit with tracked `.gitmodules` plus Gitlink entries remains rejected.
6. Existing symlink, alternates, source-drift, receipt, manifest, clean-worktree, import, authority, and launchd gates remain unchanged.
7. Existing repositories with no Gitlinks preserve current behavior.

## Verification

- reproduce that current main/desired source has Gitlinks and no tracked `.gitmodules`;
- positive inert-Gitlink bundle + two-worktree staging witness;
- negative tracked-`.gitmodules` rejection;
- negative non-empty/materialized Gitlink path rejection;
- existing R1 recovery test slice and full `tests/ops/test_mcp_gateway_durable.py`;
- `git diff --check`, Ruff, Pyright/CI before merge.

## Non-goals

No submodule support, no recursive clone/fetch, no caller-selected source, no Gateway host effect, no recovery-authority reissue, no route/workforce/security-authority changes outside this exact inert-Gitlink compatibility repair.

## Claim ceiling

Source Candidate only. Host recovery remains blocked until this Candidate is independently accepted, merged, its stable manager hash is rebound in the tracked recovery authority and DevSpace trust root, and the formal typed recovery action succeeds.