# Issue #821 — exact trusted-snapshot prerequisite for PR #833

## Authority and purpose

The Owner's continuing cutover authorization covers completion of the separately gated G9 namespace/script retirement. PR #833 is the already scoped retirement Candidate. Its required trusted controller rejects the approved packaging-only delta because the active exact transition still names historical PR #811. This separate prerequisite uses the existing exact-transition mechanism; it does not change the generic dependency validator or weaken its denial rules.

- repository: James3014/Nexus-new
- goal_id: NEXUS-THREE-REPO-CONSUMER-CUTOVER-20260907
- campaign_id: nexus-consumer-cutover-821-anchor-20260907
- task_id: 00-bind-retirement-transition
- owner_id: James3014
- coordinator_id: primary-codex-coordinator
- grant_receipt_hash: 701ef204f2d2199bd11c20f535c116a4cc67fe4431b6d8a508d40ad51d6a9536
- grant_expires_at: 2026-09-07T07:55:37.742677Z
- grant_actions: GITHUB_MERGE, TASK_CARD_COMMIT, TASK_CARD_CREATE
- eligibility: Owner-dispatched necessary prerequisite for bounded Ready Issue #821 and accepted PR #833 packaging delta
- claim_intent: MANUAL_DISPATCH
- claim_enforcement_state: UNKNOWN
- claim_mode: MANUAL_DISPATCH
- execution: governed GitHub Issue branch; native manually dispatched luna_worker / gpt-5.6-luna
- AUTO_CHAIN: false

G8 remains accepted at `4887d8f6a3faf50d6b600f2c170526e08d4bf408`; primary G8 receipt SHA-256 `855137d51b9123c4a342051e3254616957bbaadc50673d0e25e47f29c3d413d0`. PR #833's physical packaging acceptance is independently evidenced, but required CI is blocked. This card does not override that failed check and does not alter PR #833's four-file scope.

## Explicit Owner authorization and receipt rebind

Owner explicitly authorized: "trusted-anchor 從 #811 更新為 #833，綁定四個既定雜湊，保留歷史紀錄與拒絕規則。" This resolves the previous automatic-review missing-authorization block for this exact change. The formal CAS rebind superseded restored receipt `26ee19653baa2c80d8eda1448193fe938d6451e33f1dc714d760e698a5cf5533`, preserving the original scope and expiry. Historical card issuance receipt was `f89760565b37501c3eac2700c21965e71ac514fc5b2d2038bde0cefbfa7efd6b`.

## Exact admitted subject

PR number: 833 only. Current accepted packaging head: `058922099608a6a08969dd9e72117e443ea7ae6a`. Trusted base: `4887d8f6a3faf50d6b600f2c170526e08d4bf408`.

Four SHA-256 values, in existing validator order:

1. trusted pyproject.toml: `261ea0f2a2ffe179615d48acfa02ef89ed617e7970635ce39d70d8bede276b05`
2. trusted uv.lock: `5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961`
3. PR pyproject.toml: `382f05ca47059a15465515ab704d2d54b8a2a95ae83318b3f98617cd982029c3`
4. PR uv.lock: `5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961`

The lock is unchanged. The pyproject delta is exactly removal of the product package export and two nexus-certify declarations. Dependencies, build backend, extras, and dependency groups are unchanged. An ordinary subsequent PR833 main rebind may preserve this exact four-file-byte contract; any changed hash or PR number must still fail closed.

## Frozen four-file scope

Baseline: `4887d8f6a3faf50d6b600f2c170526e08d4bf408`.
Branch: `codex/issue-821-exact-retirement-transition`.

- `scripts/ops/trusted_deletion_anchor.py` — worker ownership: rotate only the active exact snapshot record to PR833; preserve PR811 as inactive historical data and retain the historical PR669 record.
- `tests/ops/test_trusted_deletion_anchor.py` — worker ownership: keep historical nodes/provenance, bind exact PR833 hashes, and preserve or extend wrong-PR/each-hash/regular-file denial coverage.
- `tasks/nexus-consumer-cutover-821-anchor-20260907/00-bind-retirement-transition.md` — primary only.
- `tasks/nexus-consumer-cutover-821-anchor-20260907/INDEX.md` — primary only.

No changes to validator control flow, workflow YAML, required-check configuration, dependencies, lock, PR833 source, other authorities, or any other file. No file deletions.

## Verification and completion

Run `python -m pytest -q tests/ops/test_trusted_deletion_anchor.py` with durable JUnit, scoped Ruff/preview formatting, and `git diff --check`. Preserve actual RED/GREEN evidence where a new regression test is used. Primary independently invokes the unchanged validator using the exact Git-sourced base/PR833 bytes, confirms the intended transition passes, and checks wrong PR, each altered hash/input, and non-regular product initializer are rejected. Confirm `_validate_trusted_dependency_contract` function bytes are unchanged.

Worker commits only its two files, reports exact source/tests, then stops; no push/PR approval/merge or grant/card mutation. Primary separately reviews the four-file diff and independently executes verification. Only terminal-success current required GitHub checks, fresh base/head/rules/reviews, exact scope/deletion evidence, and canonical standing authority permit protected expected-head/CAS merge. After its merge, PR833 is rebound and its own full required checks rerun before any retirement claim.

No general exception, security weakening, direct main push, force push, release, activation, deployment, #113/#143/#827 work or broad cleanup. Restore the predecessor grant via formal CAS after the authorized window.
