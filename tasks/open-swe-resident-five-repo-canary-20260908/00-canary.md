# Task Card 00 — Open SWE resident unattended canary

- task_id: `open-swe-resident-five-repo-canary-20260908`
- campaign_id: `open-swe-resident-five-repo-canary-20260908`
Campaign: `open-swe-resident-five-repo-canary-20260908`
- status: `ACTIVE`
- owner: `James Chen`
- commit_required: `true`
- candidate_required: `true`
- worker_may_commit: `true`
- worker_may_approve: `false`
- worker_may_integrate: `false`
- worker_may_push: `false`
- AUTO_CHAIN: `false`
- allow_deletions: `false`

## Objective

Prove that the newly activated resident External Intelligence daemon autonomously discovers one eligible Issue, uses Open SWE through OpenCLI/ChatGPT Web, creates an isolated worktree, writes one harmless test, runs exact verifiers, and publishes a verified Candidate pending independent acceptance.

## Allowed files

- `tests/ops/test_open_swe_resident_five_repo_canary_20260908.py`

## Forbidden scope

No other file may change. No deletion is allowed.

## Required behavior

Create the allowed test file with one deterministic test that asserts the ordered tuple of mounted repository IDs equals:

```python
(
    "James3014/Nexus-new",
    "James3014/devspace",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
)
```

The test is an activation witness only. It must not inspect the host config, network, credentials, browser state, or another repository.

## Verification commands

```bash
python3 -m pytest -q tests/ops/test_open_swe_resident_five_repo_canary_20260908.py
git diff --check
```

## Exit

- **PASS:** exactly one new allowed file, both verifiers pass, Candidate and acceptance packet are produced, and publication stops at independent acceptance.
- **BLOCK:** any extra path, deletion, unknown outcome, verifier failure, stale source/card binding, or attempted approval/merge/push.
