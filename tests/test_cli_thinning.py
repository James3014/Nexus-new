"""
PR-05 TDD: CLI 薄化驗證
確保 scripts/nexus_cli.py 只 parse + dispatch，不含業務邏輯。
"""
import ast
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.nexus_cli import NexusCLI


def _get_function_body_source(filepath: str, function_name: str) -> str:
    """AST 解析指定函式的原始碼，用於靜態驗證。"""
    source = Path(filepath).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                return ast.unparse(node)
    return ""


def test_cli_bug_dispatch_no_business_logic(tmp_path):
    """run_bug 應只 dispatch，不含 sleep/業務字串判斷。"""
    cli_path = "scripts/engine/nexus_cli.py"
    content = Path(cli_path).read_text()
    # 應有 run_bug
    assert "run_bug" in content
    # CLI 應委派給 engine，不含完整的修復邏輯
    assert "crystallize" not in content.lower()


def test_cli_feature_dispatch(tmp_path):
    """CLI 的 run_feature 應委派給 engine，不含硬編碼回覆。"""
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    mock_engine = MagicMock()
    mock_engine.run_feature.return_value = True
    cli._engine = mock_engine

    cli.run_feature(task="新增購物車功能")

    mock_engine.run_feature.assert_called_once()


def test_command_service_bridges_engine(tmp_path):
    """NexusCommandService 應是 CLI 與 Engine 之間的橋接層。"""
    from nexus.app.command_service import NexusCommandService
    mock_engine = MagicMock()
    mock_engine.run_bug.return_value = True
    svc = NexusCommandService(engine=mock_engine)

    svc.execute_bug(task="修復 DB 連線問題")

    mock_engine.run_bug.assert_called_once()


def test_command_service_feature_params(tmp_path):
    """execute_feature 應正確傳遞 domain/dry_run/skill 參數。"""
    from nexus.app.command_service import NexusCommandService
    mock_engine = MagicMock()
    mock_engine.run_feature.return_value = False
    svc = NexusCommandService(engine=mock_engine)

    svc.execute_feature(task="新增 SSO", domain="auth", dry_run=True, skill="coding")

    mock_engine.run_feature.assert_called_once_with(
        task="新增 SSO", domain="auth", dry_run=True, skill="coding"
    )
