---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-54-duplicate-modules
campaign_id: github-issue-54-duplicate-modules-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/54
AUTO_CHAIN: false
reconciliation: TERMINAL_RECONCILIATION
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Remove Three Duplicate Orphan Modules

## Objective

Remove three duplicate module paths whose canonical counterparts have current
callers and whose duplicate paths have none. Add no forwarding import or
compatibility shim.

## Inputs and dependencies

- Issue #54 is READY and Owner-authorized (DeepSeek auto-claim queue 5/5A).
- Evidence baseline: main `84eaa6886e0388a4e15f5b837c89e37768b14307` (fresh
  rebind per Owner directive).
- Owner directive comment (2026-08-10T03:51:48Z): self-claim authorized after
  preceding queue item reaches CANDIDATE_PR_READY or #68 is skipped on its
  serialization gate; fresh rebind + rerun caller/path/entrypoint checks before
  deletion.
- The old `tasks/github-cleanup-issue-54/00-duplicate-modules.md` card
  (governance commit `a86f564f`) is unrecoverable in current history; this new
  card is the durable rebind.
- #52 must never run concurrently: both #54 and #52 mutate
  `muse_nexus.egg-info/SOURCES.txt`.

## Allowed files

- `scripts/brain_de_entropy.py`
- `scripts/core/migration_validator.py`
- `scripts/core/drclaw_diagnosis.py`
- `muse_nexus.egg-info/SOURCES.txt` (rows referencing the deleted duplicate
  paths only)
- `tasks/github-issue-54-duplicate-modules-20260810/INDEX.md`
- `tasks/github-issue-54-duplicate-modules-20260810/01-remove-duplicate-modules.md`

Maximum changed files: 6.

## Forbidden scope

- canonical implementation changes (`nexus/core/*`, `scripts/drclaw_diagnosis.py`)
- compatibility imports/shim modules
- consolidation/refactor
- deletion of historical reports or `nexus/services/nexus_probe.py`
- deletion of unrelated SOURCES.txt stale rows
- any file outside the allowed scope above

## Required behavior

- Delete only the three authorized duplicate module paths.
- Delete only the SOURCES.txt rows referencing those deleted duplicate paths.
- Retain canonical counterparts and their current callers intact.

## Verification

- Focused ContextHub, migration-validator, operational probe, DrClaw/benchmark,
  Wiki source-integrity, and packaging tests.
- Invoke retained canonical standalone scripts with non-mutating help/dry-run
  surfaces where available.
- Full exact-base versus post-deletion regression comparison.
- Ruff on retained canonical modules and `git diff --check`.

## Required evidence and exit criteria

- Post-deletion search shows zero references to the three deleted paths.
- Canonical callers (ContextHub, migrationsafetyvalidator, DrClaw benchmark)
  still resolve.
- Focused tests and exact-base/post-deletion regression pass (identical or
  strictly fewer failures).
- Ruff and diff gate pass.

Maximum claim: three uncalled duplicate module paths removed while canonical
implementations and callers remain intact.

## Completion receipt

- Task Card authorization commit: `baf2ef096`
- implementation head: `95d72a7af`
- PR: https://github.com/James3014/Nexus-new/pull/86
- deleted: `scripts/brain_de_entropy.py`, `scripts/core/migration_validator.py`,
  `scripts/core/drclaw_diagnosis.py`
- removed the two `muse_nexus.egg-info/SOURCES.txt` rows referencing the
  deleted duplicate paths (drclaw, migration_validator)
- fresh-main rebind (`84eaa6886`); caller/path/entrypoint/AST checks rerun:
  zero references to any deleted path in source, tests, CI, CLI, docs, or
  dynamic import
- canonical callers verified: `nexus/core/context_hub.py` imports canonical
  `brain_de_entropy`; `scripts/migrationsafetyvalidator.py` imports canonical
  `nexus.core.migration_validator.MigrationValidator`; DrClaw benchmark
  references retained `scripts/drclaw_diagnosis.py`
- retained canonical modules import/load cleanly
- focused tests: ContextHub/coherence/orchestration 24 passed; CLI/wiki
  tests 42 passed with 6 pre-existing env failures (identical on base)
- exact-base/post-deletion regression: identical 16-failure set base vs
  candidate (zero regression)
- Ruff: identical 6 pre-existing findings on retained canonical modules
  (zero net-new)
- `git diff --check`: clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)

## Block classification

- `RECOVERABLE_BLOCK`: bounded regression or discovery of an active launcher
  for a duplicate path.
- `HARD_BLOCK`: canonical changes required, shim required, or scope widening.

## Terminal reconciliation (2026-08-14)

This card is terminal. Historical objective, allowed files, required behavior,
forbidden scope, verification commands, claim ceiling, and block
classification above are preserved unchanged as the implementation baseline.

- Issue #54: CLOSED/completed 2026-08-11T00:49:32Z. Owner receipts:
  `5235664084` (execution directive), `5236454757` (`CANDIDATE_PR_READY`),
  `5240453514` (contract delta / #88 resume gate).
- Dependency gate: Issue #88 / PR97 merged 2026-08-11T00:42:16Z, merge
  `cb25ef23cdcc876671803415fa3b430bad817e78`; that merge commit is exactly
  PR86's rebound base, satisfying the Owner resume gate before the final
  PR86 rebind.
- PR86: base `cb25ef23cdcc876671803415fa3b430bad817e78` -> head
  `7e0796edd430b3c834877b621ad9c4965401f911` -> merge
  `3c4f9065739e7a718bc27e1bf0d0113150946c60`; 6 files, +159/-270 (3 duplicate
  module deletions + 2 `SOURCES.txt` rows + card/INDEX); merged
  2026-08-11T00:49:30Z; closes #54.
- PR86 head exact-base checks: 5/5 success (Pyright 31447108675, Wiki
  Governance 31447108665, Ruff 31447108699, Bandit 31447108709, Pytest
  31447108704).
- Post-#88 verification on head `7e0796edd`: #88 exact selector maps all four
  cleanup paths without fallback; focused ContextHub, migration, DrClaw,
  source-inventory, and policy tests 31 passed; retained
  `scripts/migrationsafetyvalidator.py` gatekeeper surface pass; retained
  `scripts/drclaw_diagnosis.py --help` pass; `git diff --check` pass.
- Previous current main (historical rebind receipt, post-PR236):
  `cdf2570ede5ae218f36f886b696c8da45458043a`.
- Current main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; merge ancestry
  verified via `git merge-base --is-ancestor`.
- Marker: `DUPLICATE_MODULE_CLEANUP_PROVEN`.
- Claim ceiling: cleanup-only / proven-only. No runtime, route, Workforce,
  provider, approval, integration, merge, release, or production authority.
