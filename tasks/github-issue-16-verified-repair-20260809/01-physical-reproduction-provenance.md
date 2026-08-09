---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: issue16-g1-physical-reproduction
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G1 Physical Reproduction Provenance

## Objective

Represent physical, descriptive, pre-supplied, and skipped reproduction evidence
without allowing prose, an unexecuted script, or `skip_reproduction` to qualify as
physical baseline proof.

## Dependencies

None. Base is fresh Issue #16 collaboration main. Preserve legacy compatibility.

## Allowed files

- `nexus/services/local_heal/context.py`
- `nexus/services/local_heal/interface.py`
- `nexus/services/local_heal/phases/reproduction.py`
- `nexus/services/local_heal/reproduction.py`
- `tests/unit/test_reproduction_phase.py`
- `tests/unit/test_reproduction_runner.py`

Maximum changed files: 6.

## Forbidden scope

Planner/workforce, Candidate approval/integration, route authority, lifecycle schema,
public claims, and all later G2-G6 files.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/test_reproduction_phase.py tests/unit/test_reproduction_runner.py`
- `git diff --check`

## Required evidence and exit

Typed provenance and deterministic command/script/source identity, the runner's
actual exit status, and evidence hash. Source identity must bind the Git
revision/workspace rather than merely hashing a filesystem path. Physical execution is distinguishable from descriptive,
pre-supplied, and skipped evidence. Maximum claim: provenance recorded.

## Completion evidence

- Accepted authority hash before completion writeback:
  `9e37e54b4bf51cc53fc86f75915b9488c222efcbfbac03d682fc1843c57858c2`.
- Reconciled base: `b6644968e56563095a3ac935f6236040aef6f1cf`.
- Rebased implementation commit:
  `7ac9a4db2bdd8cee989e0b9aae462e3d5b74f3e8`.
- Exact G1 suite: `31 passed`; Ruff and `git diff --check` passed.
- Negative controls reject timeout, pre-subprocess exception, ordinary crash,
  dormant assertions, untrusted output markers, and boolean `SystemExit`.
- Independent reviewer verdict: `ACCEPT`, no reproducible G1 P0/P1.
- Maximum claim remains physical reproduction provenance recorded; no same-
  oracle, regression, adequacy, mutation, or final repair claim is made.

## Block classification

`RECOVERABLE_BLOCK` for bounded test/contract defects; `HARD_BLOCK` for authority or
compatibility conflict.
