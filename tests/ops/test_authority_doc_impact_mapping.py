"""Pin the Issue #1896 mapping: authority docs select authority-text/context-budget tests."""

from __future__ import annotations

import pytest

from scripts.ops.pr_impact_gate import build_impact_plan

AUTHORITY_TEXT_TARGETS = (
    "tests/ops/test_bootstrap_authority_files.py",
    "tests/ops/test_bootstrap_context_budget.py",
    "tests/ops/test_codex_task_context_index.py",
    "tests/ops/test_fast_start_consumer_contract.py",
)

AUTHORITY_DOC_PATHS = (
    "AGENTS.md",
    "MUSE_PROTO.md",
    "CLAUDE.md",
    "GEMINI.md",
    "SOUL.md",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/domain.md",
    "docs/agents/HANDOFF_PROTOCOL.md",
)


@pytest.mark.parametrize("path", AUTHORITY_DOC_PATHS)
def test_authority_doc_change_selects_authority_text_tests(path: str) -> None:
    plan = build_impact_plan([path])

    missing = [target for target in AUTHORITY_TEXT_TARGETS if target not in plan.pytest_targets]
    assert not missing, f"{path} did not select {missing}; got {plan.pytest_targets}"
    assert plan.pytest_required is True
