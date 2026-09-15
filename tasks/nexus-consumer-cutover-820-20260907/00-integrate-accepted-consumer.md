# Issue #820 — integrate independently accepted consumer PR #830

## Objective and authority

Integrate only the accepted consumer delta in PR #830 through normal protected GitHub merge. The Owner explicitly authorized this milestone and the temporary canonical grant switch. The primary coordinator owns this integration; delegated workers cannot approve or merge.

- goal_id: NEXUS-THREE-REPO-CONSUMER-CUTOVER-20260907
- campaign_id: nexus-consumer-cutover-820-20260907
- task_id: 00-integrate-accepted-consumer
- repository: James3014/Nexus-new
- owner_id: James3014
- coordinator_id: primary-codex-coordinator
- grant_receipt_hash: f89760565b37501c3eac2700c21965e71ac514fc5b2d2038bde0cefbfa7efd6b
- grant_expires_at: 2026-09-07T07:55:37.742677Z
- allowed_grant_actions: GITHUB_MERGE, TASK_CARD_COMMIT, TASK_CARD_CREATE
- issue_eligibility: Owner-dispatched bounded open contract with explicit acceptance and frozen physical paths; no label supplies authority
- claim_intent: MANUAL_DISPATCH
- claim_enforcement_state: UNKNOWN
- claim_mode: MANUAL_DISPATCH
- workforce_binding: coordinator-only integration; no new Nexus worker admission or implementation dispatch
- AUTO_CHAIN: false

Prior implementation used its separate explicit direct-delegated authorization. This card supplies no retrospective worker authority.

## Frozen subject and allowed scope

- baseline_main: `491660f2a95eb04e68683e1648c2f9a20744a52a`
- independently accepted implementation head: `54808cf17f0d98ae39192ceeba819d3ce3103dae`
- implementation tree: `778dd56d4789e0d971625e58b308e3a1aee1c810`
- maximum_files: 9

Allowed files:

- `docs/ops/OPEN_SWE_STANDALONE_CONSUMER.md`
- `nexus/services/open_swe_external_intelligence.py`
- `scripts/ops/configs/external_intelligence_open_swe_activation_v1.json`
- `scripts/ops/external_intelligence_service.py`
- `tasks/nexus-consumer-cutover-820-20260907/00-integrate-accepted-consumer.md`
- `tasks/nexus-consumer-cutover-820-20260907/INDEX.md`
- `tests/services/test_external_intelligence_service.py`
- `tests/services/test_open_swe_external_intelligence.py`
- `tests/services/test_open_swe_worker_transport.py`

Accepted implementation file SHA-256 bindings:

- `docs/ops/OPEN_SWE_STANDALONE_CONSUMER.md`: `f09a0c877d99b65782207f806d71f0e4378679618ef8e3a8d5acad5ec92e61d5`
- `nexus/services/open_swe_external_intelligence.py`: `5b8e8aeefe16a63e8f35609bbcfd026f7e9faaea95617f4e76cfec7b5425701d`
- `scripts/ops/configs/external_intelligence_open_swe_activation_v1.json`: `1397c19fb95ea98fc5b7701b76c6e1b9c2738524f0ac04875ad10140295b3550`
- `scripts/ops/external_intelligence_service.py`: `ea1d0ff0085d68a70529e601da20ee94047bb5a4bcce54ba315f5ae174128152`
- `tests/services/test_external_intelligence_service.py`: `a5b1a288c4b1eb033309a972e7d42a36a2cca3d0b63e175ead0f234fad1d2aee`
- `tests/services/test_open_swe_external_intelligence.py`: `0c8be9ec45518410037202d88b71dca4aa400d9dd27ec91dabb299d775c8d704`
- `tests/services/test_open_swe_worker_transport.py`: `7ce069bdd928089ed38e92f7ad39fb3a7a9a9f87223552d199697bb3c9e82b46`

Only this Task Card and INDEX are newly authored at this integration step. Preserve the accepted implementation blobs. Ordinary main drift requires exact rebinding and renewed checks; semantic or authority drift requires fresh independent acceptance.

## Verification and acceptance

- `python -m pytest -q tests/services/test_external_intelligence_service.py tests/services/test_open_swe_external_intelligence.py tests/services/test_open_swe_worker_transport.py`
- Changed Python Ruff check and preview-format check; prior executed focused evidence remains bound to the exact preserved implementation blobs.
- `git diff --check` and exact allowed-path/file-count audit; no deleted files.
- Fresh GitHub exact-base impact gate, trusted verifier, full published-history secret audit and every other current ruleset-required check must reach terminal SUCCESS on the final PR head. Baseline debt may remain only under the existing exact-base classifier with zero new failures; never claim all tests passed.
- Fresh PR/base/head/tree/diff, current main, review submissions and unresolved threads, dependencies, overlap, branch rules, independent acceptance, and canonical grant validation are mandatory immediately before expected-head/CAS merge.
- The live `github_complete_pull_request` surface is the preferred completion action; it never creates authority.

## Physical consumer evidence and claim boundary

The coordinator retains the installed-artifact consumer evidence and exact-head CI receipts in `/private/tmp/nexus-cutover-integration-packet-20260907` and `/private/tmp/nexus-cutover-ci-final-20260907`. Artifact manifests are evidence locators, not independent authority. Worker PASS does not replace coordinator acceptance.

No direct push/force push/deletion of main, unrelated cleanup, #113/#143 mutation, runtime activation, local lifecycle approval, G9 legacy deletion, release, deployment, production or public Stable claim. No unrelated unmerged PR is silently absorbed.

## Exit and reconciliation

Read back the real GitHub merge and new main; verify ancestry and exact consumer blobs, and persist the final receipt with card hash and PR/check bindings. Reconcile the owning Issue and parent #822 only to the physically proven consumer state. G8 terminal requires all three consumer lanes. G9 remains a separate subsequent gate. Restore the predecessor standing-grant context through formal CAS after the authorized integration window.
