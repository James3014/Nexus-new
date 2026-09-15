# Task Card: cli-publication-guard

artifact_authority: current
task_id: `cli-publication-guard`
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

Owner reaffirmed all goal-completion operations in this thread. Repair confirmed CliWorkerRequest acceptance of gh issue comment without exact publication authority, including analogous follow-up public write verbs and supported command flag variants. Luna implements; controller independently verifies. Preserve legitimate read-only worker CLI use, existing internal collaboration authority and all Owner signature/durability controls. Tests must exercise real request constructor and prove denial before process spawn using safe fixtures only. Do not claim arbitrary shells or interpreters physically incapable of publication; no generic sandbox redesign, no real publication, no merge. Produce RED/GREEN scoped immutable commit.

## Allowed files

- `nexus/executors/cli_worker.py`
- `tests/nexus/executors/test_cli_worker.py`
- `docs/governance/OWNER_REPRESENTATION.md`

## Verification commands

```bash
python -m pytest -q tests/nexus/executors/test_cli_worker.py tests/nexus/orchestrator/test_owner_representation.py
python -m ruff check nexus/executors/cli_worker.py tests/nexus/executors/test_cli_worker.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
