"""LocalHeal model sandbox calls bind grants to the selected directory identity."""

import ast
from pathlib import Path

import pytest

_MODULES = (
    "evaluation_gate.py",
    "isolated_verifier.py",
    "micro_verifier.py",
    "reproduction.py",
)
_ROOT = Path(__file__).parents[3] / "nexus/services/local_heal"


def _sandbox_work_dirs(source: str) -> list[ast.expr]:
    tree = ast.parse(source)
    return [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_model_argv"
        for keyword in node.keywords
        if keyword.arg == "work_dir"
    ]


@pytest.mark.parametrize("module", _MODULES)
def test_every_local_heal_model_root_is_pinned_before_sandbox_entry(module):
    source = (_ROOT / module).read_text(encoding="utf-8")
    work_dirs = _sandbox_work_dirs(source)

    assert work_dirs, f"{module} has no model sandbox roots"
    unpinned = [
        node
        for node in work_dirs
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PinnedRoot"
        )
        and not (isinstance(node, ast.Name) and node.id == "pinned_repo")
    ]
    assert not unpinned, f"{module} passes an unpinned root to the model sandbox"
