# Issue #822 — integrate independently accepted consumer PR #831

## Objective and authority

Integrate only the accepted consumer delta in PR #831 through normal protected GitHub merge. The Owner explicitly authorized this milestone and the temporary canonical grant switch. The primary coordinator owns this integration; delegated workers cannot approve or merge.

- goal_id: NEXUS-THREE-REPO-CONSUMER-CUTOVER-20260907
- campaign_id: nexus-consumer-cutover-822-20260907
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
- independently accepted implementation head: `02610a84f33b59ab59de28f7260cf1c0c0f4994b`
- implementation tree: `eeb7df1b62b8b79bec8aef7030c5232c6a5b6156`
- maximum_files: 5

Allowed files:

- `.github/actions/nexus-certify/action.yml`
- `README.md`
- `tasks/nexus-consumer-cutover-822-20260907/00-integrate-accepted-consumer.md`
- `tasks/nexus-consumer-cutover-822-20260907/INDEX.md`
- `tests/product/test_github_action_core_binding.py`

Accepted implementation file SHA-256 bindings:

- `.github/actions/nexus-certify/action.yml`: `05b342d5860246e13e09cee94cafc7989aab9f96c6134399e801e69ec3662305`
- `README.md`: `ae3a9da25ce8a0729a28f65e0bbafe1b1a0165fbb28a073e33b92d7efdb34cc9`
- `tests/product/test_github_action_core_binding.py`: `8dd749fadde36a3b6b28abd70135e4a79ce11219b4be73b1292c2dafffa330ae`

Only this Task Card and INDEX are newly authored at this integration step. Preserve the accepted implementation blobs. Ordinary main drift requires exact rebinding and renewed checks; semantic or authority drift requires fresh independent acceptance.

## Verification and acceptance

- `python -m pytest -q tests/product/test_github_action_core_binding.py`
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
