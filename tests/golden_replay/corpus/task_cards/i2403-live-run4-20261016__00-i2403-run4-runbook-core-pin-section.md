# Task Card: i2403-run4-runbook-core-pin-section

artifact_authority: current
task_id: `i2403-run4-runbook-core-pin-section`
owner: James Chen
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Add a short section titled "When the pinned Core changes" to docs/runbooks/declaring_expected_evidence_universe.md, placed before the "Checking the result" section. Keep it to 3-6 lines of plain prose. It must say: when CANONICAL_CORE_REVISION is bumped, the host uses the pinned Core's own expected_universe_identity and core_identity rather than a host-side copy (#2247); and the deployer sets PYTHONPYCACHEPREFIX outside the Core checkout so a planted .pyc file in the Core tree cannot execute (#2255). Change nothing else in the file and no other file.

## Allowed files

- `docs/runbooks/declaring_expected_evidence_universe.md`

## Verification commands

```bash
git diff --check
```

## Expected evidence

```nexus-expected-evidence
{"subjects":[{"applicability":"APPLICABLE","evidence_kind":"verifier-run","logical_subject_id":"git diff --check","requirement_mode":"REQUIRED"}],"universe_generation":1}
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
