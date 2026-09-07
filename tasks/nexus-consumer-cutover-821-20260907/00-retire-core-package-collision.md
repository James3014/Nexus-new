# Issue #821 — retire duplicate Core distribution ownership

## Authority and bounded objective

The Owner authorized continuation of the three-repository cutover goal through a separately gated legacy retirement. G8 is independently accepted at `4887d8f6a3faf50d6b600f2c170526e08d4bf408`, tree `b96eed5ac6121d155e5959ab410f62400690df1d`.

- repository: James3014/Nexus-new
- goal_id: NEXUS-THREE-REPO-CONSUMER-CUTOVER-20260907
- campaign_id: nexus-consumer-cutover-821-20260907
- task_id: 00-retire-core-package-collision
- owner_id: James3014
- coordinator_id: primary-codex-coordinator
- grant_receipt_hash: f89760565b37501c3eac2700c21965e71ac514fc5b2d2038bde0cefbfa7efd6b
- grant_expires_at: 2026-09-07T07:55:37.742677Z
- grant_actions: GITHUB_MERGE, TASK_CARD_COMMIT, TASK_CARD_CREATE
- issue_eligibility: Owner-dispatched bounded Issue #821; G8 dependency satisfied by physical primary receipt
- claim_intent: MANUAL_DISPATCH
- claim_enforcement_state: UNKNOWN
- claim_mode: MANUAL_DISPATCH
- execution: governed GitHub Issue branch; native Codex delegated worker, no local Nexus lifecycle outcome
- implementation_worker: native luna_worker / gpt-5.6-luna, manually dispatched by primary
- AUTO_CHAIN: false

G8 receipt: `/private/tmp/nexus-g8-final-reconciliation-20260907/controller-final-acceptance.json`, SHA-256 `855137d51b9123c4a342051e3254616957bbaadc50673d0e25e47f29c3d413d0`.
Advisory cache #549 revision 22 has no #821 entry; normal fresh authoritative discovery applies. Current Issue #821 is the bounded namespace/script retirement contract. This card neither widens that contract nor grants delegated-worker acceptance/merge authority.

## Frozen scope

Baseline: `4887d8f6a3faf50d6b600f2c170526e08d4bf408`.
Branch: `codex/issue-821-core-namespace-retirement`.
Maximum four changed files:

1. `pyproject.toml`
2. `tests/ops/test_issue_821_core_namespace_retirement.py`
3. `tasks/nexus-consumer-cutover-821-20260907/00-retire-core-package-collision.md`
4. `tasks/nexus-consumer-cutover-821-20260907/INDEX.md`

Worker owns only files 1–2. Primary owns this card and INDEX. Remove only the legacy wheel's `product` package export and both duplicate `nexus-certify` entry-point declarations. Preserve the `nexus` lab command, all source files, dependencies, lock files, historical tests/receipts, and unrelated state. No file deletion is authorized. The separate retirement delta is removal of three packaging declarations, not a source-tree purge.

## Behavioral contract and verification

- Build the actual legacy wheel; it must contain no `product/` payload and no `nexus-certify` console declaration. Preserve the `nexus` entry point and `nexus`/`scripts` payload.
- Add meaningful regression tests in the new test file, with an actual RED run against the baseline and GREEN after the metadata change. Tests must run in normal CI without a private `/tmp` wheel dependency.
- Focused command: `python -m pytest -q tests/ops/test_issue_821_core_namespace_retirement.py` with JUnit retained. Run changed-test Ruff and preview format checks plus `git diff --check`.
- Primary separately runs the physical verifier against an exact canonical `nexus-core` wheel and the built retirement wheel. Both install orders must leave only canonical Core owning `product` and `nexus-certify`; verify RECORD hashes, isolated CLI help, and Core survival after legacy uninstall. No copied venv, ambient source imports, or fabricated physical PASS.
- Canonical Core wheel SHA-256: `57abfa980b4fced3f66ce788ff373d96b8315ae26e44660050441d2394991493`. Baseline legacy wheel SHA-256: `d52a2d5a0d278c70644342d8f1c83f19ad5ccfa531cef06384b354dda8b7eac4`, with 33 overlapping `product/` entries and duplicate console ownership.
- Existing `tests/ops/test_clean_wheel_entrypoints.py` baseline failures are not in repair scope. Required exact-base CI must show zero new failures; never claim all tests green from baseline-debt success.
- Commit only scoped files. Primary inspects exact diff/tree, deletion scope, verifier artifacts, current required checks/rules/reviews, and canonical standing authority before expected-head/CAS protected merge. Ordinary drift requires fresh requalification.

## Exit and limits

Worker returns the bounded commit, test results, exact built wheel path/hash and evidence, then stops. Worker cannot approve, merge, release, activate services, alter grants/cards, or claim G9 terminal.
Primary reads back merged main and exact packaging blobs, preserves historical source/provenance, and may then record `CORE_LEGACY_NAMESPACE_RETIREMENT_VERIFIED`. No direct main push, force push, #113/#143/#827 mutation, broad cleanup, daemon/native host activation, public Stable/release, or deployment. Restore the predecessor grant context through formal CAS after the authorized window.
