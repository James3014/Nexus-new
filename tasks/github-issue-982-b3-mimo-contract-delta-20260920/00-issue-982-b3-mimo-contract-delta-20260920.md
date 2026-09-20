# Task Card: issue-982-b3-mimo-contract-delta-20260920

artifact_authority: current
task_id: `issue-982-b3-mimo-contract-delta-20260920`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Update only the Wave B B3 governance contract to replace the stale big-pickle witness identity with the already-merged #1032/#1039 canonical MiMo route, require current Gateway binding to d7b2e359 or verified descendant before canary effect, preserve the 4-to-1 read-only tool-authority intervention and same-grant widening negative, and preserve AUTO_CHAIN=false. No production source mutation.

## Allowed files

- `docs/specs/ISSUE_982_WAVE_B_GOVERNED_TOOL_AUTHORITY_001.md`
- `tasks/github-issue-982-wave-b-20260919/02-governed-opencode-runtime-witness.md`
- `tasks/github-issue-982-wave-b-20260919/INDEX.md`

## Verification commands

```bash
python -m pytest tests/engine/test_canonical_task_seam.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
