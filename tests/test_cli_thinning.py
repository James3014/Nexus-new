from pathlib import Path
"""
PR-05 TDD: CLI 薄化驗證
確保 scripts/engine/nexus_cli.py 只 parse + dispatch，不含業務邏輯。
"""
import ast
import pytest
from unittest.mock import MagicMock
from unittest.mock import patch
from nexus.app.command_service import TaskRequest
from nexus.engine.config import EngineConfig


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


def test_command_service_bridges_engine(tmp_path):
    """NexusCommandService 應是 CLI 與 Engine 之間的橋接層。"""
    from nexus.app.command_service import NexusCommandService
    mock_engine = MagicMock()
    mock_engine.run_bug.return_value = True
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)

    svc.execute_bug(TaskRequest(task="修復 DB 連線問題"))

    mock_engine.run_bug.assert_called_once()


def test_command_service_feature_params(tmp_path):
    """execute_feature 應正確傳遞 domain/dry_run/skill 參數。"""
    from nexus.app.command_service import NexusCommandService
    mock_engine = MagicMock()
    mock_engine.run_feature.return_value = False
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)

    svc.execute_feature(TaskRequest(task="新增 SSO", domain="auth", plan_only=True, skill="coding"))

    mock_engine.run_feature.assert_called_once_with(
        task="新增 SSO",
        context={"delivery_mode": "standard"},
        domain="auth",
        dry_run=True,
        skill="coding",
    )


def test_command_service_high_delivery_requires_verify_commands(tmp_path):
    from nexus.app.command_service import NexusCommandService
    from nexus.delivery.models import CompletionResult, CompletionStatus, TaskLevel

    mock_engine = MagicMock()
    mock_engine.run_bug.return_value = True
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)
    with patch("nexus.app.command_service.suggest_verification_commands", return_value=["/bin/echo ok"]), \
         patch(
             "nexus.app.command_service.evaluate_completion",
             return_value=CompletionResult(
                 task_name="bug-1",
                 task_level=TaskLevel.SMALL_FIX,
                 status=CompletionStatus.VERIFIED,
                 gate_passed=True,
                 summary="ok",
                 verification_records=[],
             ),
         ), \
         patch(
             "nexus.app.command_service.write_report_bundle",
             return_value=(tmp_path / "r.json", tmp_path / "r.md"),
         ):
        ok = svc.execute_bug(
            TaskRequest(
                task="修復 DB 連線問題",
                delivery_mode="high",
                verify_commands=[],
            )
        )

        assert ok is True
        assert svc.last_completion_result is not None
        assert svc.last_completion_result.status.value == "verified"
        assert svc.last_effective_verify_commands == ["/bin/echo ok"]


def test_command_service_high_delivery_uses_rust_suggestions(tmp_path):
    from nexus.app.command_service import NexusCommandService
    from nexus.delivery.models import CompletionResult, CompletionStatus, TaskLevel

    rust_dir = tmp_path / "nexus-core"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname='nexus-core'\n", encoding="utf-8")
    mock_engine = MagicMock()
    mock_engine.run_feature.return_value = True
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)
    seen = {}

    def fake_evaluate(request):
        seen["commands"] = request.verification_commands
        return CompletionResult(
            task_name=request.task_name,
            task_level=TaskLevel.FEATURE,
            status=CompletionStatus.PARTIALLY_VERIFIED,
            gate_passed=False,
            summary="failed",
            verification_records=[],
        )

    with patch("nexus.app.command_service.evaluate_completion", side_effect=fake_evaluate), \
         patch(
             "nexus.app.command_service.write_report_bundle",
             return_value=(tmp_path / "r.json", tmp_path / "r.md"),
         ):
        ok = svc.execute_feature(
            TaskRequest(
                task="fix rust leak in nexus-core",
                delivery_mode="high",
                verify_commands=[],
            )
        )

        assert ok is False
        assert seen["commands"] == ["cargo test --manifest-path nexus-core/Cargo.toml"]
