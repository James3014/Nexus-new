---
artifact_authority: current
owner: James Chen
status: IMPLEMENTED_PENDING_CANARY
task_id: github-issue-10-openwiki-hardening-canary
campaign_id: github-issue-10-openwiki-hardening-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/10
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: OpenWiki Hardening and Canary

## Objective

Correct Issue #10's source-verified OpenWiki defects, protect them with focused
regressions, and prove pinned OpenWiki regeneration does not reintroduce stale
symbols, recipes, taxonomy, counts, authority semantics, or invented workflow
names.

## Inputs and dependencies

- Issue #10 is Ready/In Progress.
- Current reconciled base: `b14a929ee74586cdfc2d595412aabe2882745039`.
- OpenWiki remains `derived_non_authoritative`.

## Allowed files

- `openwiki/INSTRUCTIONS.md`
- `openwiki/governance/gates-and-contracts.md`
- `openwiki/quickstart.md`
- `openwiki/routing/capability-planner.md`
- `openwiki/runtime/mcp-gateway.md`
- `openwiki/testing/validation-and-benchmarks.md`
- `openwiki/workflows/github-actions.md`
- `openwiki/workflows/index.md`
- `tests/ops/test_openwiki_source_contract.py`
- `tasks/github-issue-10-openwiki-hardening-20260809/INDEX.md`
- `tasks/github-issue-10-openwiki-hardening-20260809/00-openwiki-hardening-canary.md`

Maximum changed files: 11.

## Forbidden scope

- `nexus_wiki_vault/`
- Runtime source, route authority, lifecycle, schema, or workforce policy
- `AGENTS.md`, `CLAUDE.md`, workflow source, generated secret/state files
- Runtime activation, approval, release, or public-authority claims

## Verification

- `.venv/bin/python -m pytest -q tests/ops/test_openwiki_source_contract.py tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `.venv/bin/ruff check tests/ops/test_openwiki_source_contract.py`
- Two independent `openwiki@0.3.1 code --update --print` runs on the same exact
  pushed branch, with controlled files restored and output diffs compared
- Canonical Wiki/OpenWiki gates and `git diff --check`

## Required evidence

- Exact branch head and card SHA-256
- Generator run identities and output manifests
- No changes outside `openwiki/` after controlled-file restore
- Deterministic repeat and no protected-defect recurrence
- Independent primary-agent review

## Exit criteria

- Issue #10 acceptance tests pass.
- Repeat generator output is clean or identical and source-verified.
- No governed Wiki/runtime surface changes.

## Block classification

- `RECOVERABLE_BLOCK`: generator output requires bounded correction.
- `HARD_BLOCK`: generator requires forbidden authority/runtime mutation.
