# Task Card: EIA nightly eia-nightly-20261028-i2963

## Identity

- task_id: `eia-nightly-20261028-i2963`
- campaign_id: `eia-nightly`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false
- allow_deletions: false
- execution_lane: `DIRECT_DELEGATED`
- capability_disposition: `EXTEND_EXISTING`
- capability_ids: `nexus_core_domain_runtime`

## Objective

Resolve GitHub Issue #2963: test: quote sys.executable in the 2956 host-interpreter sandbox test. Quote sys.executable in the 2956 host-interpreter sandbox test so a path with spaces cannot make it pass vacuously (test only).

The full problem statement is the body of Issue #2963 (difficulty: easy).

## Allowed files

- `tests/engine/test_model_sandbox_host_venv_2956.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2963 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q -p no:cacheprovider tests/engine/test_model_sandbox_host_venv_2956.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
