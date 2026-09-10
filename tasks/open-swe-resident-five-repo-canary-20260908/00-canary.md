# Task Card 00 — Open SWE resident unattended canary

- task_id: `open-swe-resident-five-repo-canary-20260908`
- campaign_id: `open-swe-resident-five-repo-canary-20260908`
Campaign: `open-swe-resident-five-repo-canary-20260908`
- status: `COMPLETED_AT_BOUNDED_CLAIM_CEILING`
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


## r28 bounded completion evidence

The canary reached the recorded bounded Candidate state with these exact bindings:

- Nexus-new base `a59b8ab23a91ae4470300a34b4691567255c12af`
- Runtime main `3eb673bfcfd874043a70743e34761784fda39c10`
- Operation `96b83c02de43ff8e6bc37d49e0efabd3f113ac60135ea214c367094b24806574`
- Durable effect `effect_ef0802c64e2a8e8f8a65ccb696adf1b0d9d50b21a06348e10d931a038d88af68`
- Unit Candidate `2d41308d27999f210627981a933f8f0da95e54f0`; Task Candidate `c5979ffbc664e019f6790bc5f6c84210749fa43c`; tree `a85cd07d4dc2d17f7551869565fcbc2fcf6512f3`
- Task Card hash `d39a297583ebf37cdfbd0efa09a8c16f3ecf11ec7b9ced8a43dcc07d18d31fb1`
- Whole-task verification `512530748d61ea0537f5019956bbf07bbbec33a9e724a0790bdeb15cd47d3c6d` (`PASS`)
- Worker receipt `b893c704f2b8e2632d94c203f44a25a87f32dc9e9758ab5f9ac2d1ec0fb4d2b1`; five-mount receipt SHA `89d36c80399c15a4fe306c28318f4108d4b64cd90a1c94c643e8892bf4576f53`
- Final rollback/restore receipt SHA `1b7ce771a8b4aa14e94045a36b0a9aeeabcd9ed09b4a986ce1d87b1326907888`; closure capsule `ec02d8d07d681b88751ba20b7e1fbb8afdf1e103882554926fd5a4d6511a7694`
- Resident final READY run `0eb9a96de9f64454b21362a141a7d41a`

The original acceptance packet records `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` with gate `PENDING_INDEPENDENT_ACCEPTANCE`; controller acceptance receipt `9638ef72801a31ca84560b8b7d3d99bd512925b593f7b535b993b762b5860cf6` later records `CANDIDATE_ACCEPTED_FOR_R28_ACTIVATION_WITNESS`. `AUTO_CHAIN=false` remains in force. This canary closeout does not authorize approval, merge, push, release, production readiness, or mutation of the other mounted repositories.
