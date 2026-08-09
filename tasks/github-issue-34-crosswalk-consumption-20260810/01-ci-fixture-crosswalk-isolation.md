---
artifact_authority: current
owner: James Chen
status: READY
task_id: github-issue-34-crosswalk-consumption-ci-fixture
campaign_id: github-issue-34-crosswalk-consumption-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/34
source_pr: https://github.com/James3014/Nexus-new/pull/37
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Repair Card: Isolate the Missing-key-path Fixture from Crosswalk Inputs

## Objective

Repair the one exact-base regression introduced by PR #37 without weakening
production fail-closed crosswalk behavior. The existing test for missing key
paths uses a synthetic repository that intentionally has no OpenWiki or
authority manifest; it must isolate the unrelated crosswalk dependency.

## Evidence

- PR #37 exact base: `15c2f7c78c7e7a54327ab4aeaf8c2fdaa0751592`.
- Exact head: `97fb66826a93d3bdc6748de643b579860ba08965`.
- CI classification: exactly one new failure,
  `tests.ops.test_wiki_closure_gates::test_wiki_coverage_audit_ignores_missing_key_paths`.
- Failure: production correctly rejected missing synthetic `repo/openwiki`.
- Production crosswalk compiler/validator and its fail-closed contract must not
  be relaxed for this unrelated fixture.

## Allowed files

- `tests/ops/test_wiki_closure_gates.py`
- `tasks/github-issue-34-crosswalk-consumption-20260810/INDEX.md`
- `tasks/github-issue-34-crosswalk-consumption-20260810/01-ci-fixture-crosswalk-isolation.md`

Maximum changed files: 3.

## Forbidden scope

- production code
- OpenWiki, authority manifest, compiler, coverage policy, or CI workflow
- bypassing or weakening missing/stale/tampered crosswalk failure
- unrelated baseline failures reported by the exact-base classifier

## Required behavior and verification

- Patch only the synthetic missing-key-path test so its crosswalk dependency is
  deterministic and explicit; do not alter what the test is asserting.
- `uv run pytest -q tests/ops/test_wiki_closure_gates.py::test_wiki_coverage_audit_ignores_missing_key_paths tests/ops/test_openwiki_authority_crosswalk.py tests/ops/test_openwiki_source_contract.py tests/ops/test_wiki_coverage_policy.py`
- `uv run ruff check tests/ops/test_wiki_closure_gates.py`
- `uv run ruff format --check tests/ops/test_wiki_closure_gates.py`
- `git diff --check`
- exact allowed-file and deletion audit

## Exit criteria

- The exact new CI failure passes.
- Existing 44 crosswalk tests remain green.
- No production or authority input changes.
- Independent review confirms no production fail-open path.

## Block classification

- `RECOVERABLE_BLOCK`: bounded fixture defect.
- `HARD_BLOCK`: repair requires production fail-open or authority widening.
