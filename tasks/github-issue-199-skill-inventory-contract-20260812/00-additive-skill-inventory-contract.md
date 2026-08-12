# Task Card: Issue 199 Additive Skill Inventory Contract

## Scope

Allowed:
- `tests/ops/test_skill_file_contract.py`
- this campaign's Task Card and INDEX

Forbidden:
- `.agents/skills/**`
- runtime, catalog, route, Workforce, lifecycle, workflow, selector implementation
- PR #138 content
- approval/integration/release authority

## Goal

Replace brittle hard-coded repository skill/desriptor counts with assertions derived from the physical `.agents/skills` inventory while preserving every existing fail-closed descriptor rule and Yang's stable id assertion.

## Verification

- `pytest -q tests/ops/test_skill_file_contract.py`
- `ruff check tests/ops/test_skill_file_contract.py`
- `ruff format --check tests/ops/test_skill_file_contract.py`
- `git diff --check`
- exact scope audit

AUTO_CHAIN=false.
Claim ceiling: `ADDITIVE_SKILL_INVENTORY_CONTRACT_CANDIDATE_ONLY`.
