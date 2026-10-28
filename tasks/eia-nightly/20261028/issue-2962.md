# Task Card: EIA nightly eia-nightly-20261028-i2962

## Identity

- task_id: `eia-nightly-20261028-i2962`
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

Resolve GitHub Issue #2962: test: pin EnvDenoiser model-output refusal label when both a missing module and an astropy marker appear. Pin the model-output refusal label when output has both a missing module and an astropy build marker (test only).

The full problem statement is the body of Issue #2962 (difficulty: easy).

## Allowed files

- `tests/unit/local_heal/test_env_denoiser_model_output_2952.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2962 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q -p no:cacheprovider tests/unit/local_heal/test_env_denoiser_model_output_2952.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
