"""
PR-04 TDD: Bug/Feature 共用 Pipeline 等價驗證
確保 run_bug/run_feature 都委派給同一個 _run_task_pipeline，不含重複分支邏輯。
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from nexus.engine.coordinator import NexusEngine


from nexus.engine.config import EngineConfig


@pytest.fixture
def engine(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cases").mkdir()
    return NexusEngine(EngineConfig(project_root=project_root))


def test_run_bug_delegates_to_pipeline(engine):
    """run_bug 必須呼叫 _run_task_pipeline，不能自行實作完整流程。"""
    engine.pipeline = MagicMock()
    engine.pipeline.run.return_value = True
    engine.reporter = MagicMock()

    result = engine.run_bug("bug-001", desc="修復登入錯誤")

    engine.pipeline.run.assert_called_once()
    call_kwargs = engine.pipeline.run.call_args
    assert call_kwargs is not None
    assert result is True


def test_run_feature_delegates_to_pipeline(engine):
    """run_feature 必須呼叫 _run_task_pipeline，不能自行實作完整流程。"""
    engine.pipeline = MagicMock()
    engine.pipeline.run.return_value = True
    engine.reporter = MagicMock()

    result = engine.run_feature("新增會員功能")

    engine.pipeline.run.assert_called_once()
    assert result is True


def test_pipeline_task_type_mapping(engine):
    """bug 任務傳入 task_type='bug'，feature 傳入 task_type='feature'。"""
    engine.pipeline = MagicMock()
    engine.pipeline.run.return_value = False
    engine.reporter = MagicMock()

    engine.run_bug("b1", desc="bug desc")
    bug_call = engine.pipeline.run.call_args
    assert bug_call.kwargs.get("task_type") == "bug" or (
        len(bug_call.args) > 1 and bug_call.args[1] == "bug"
    )

    engine.pipeline.run.reset_mock()
    engine.run_feature("feat desc")
    feat_call = engine.pipeline.run.call_args
    assert feat_call.kwargs.get("task_type") == "feature" or (
        len(feat_call.args) > 1 and feat_call.args[1] == "feature"
    )


def test_no_duplicate_crystallize_in_coordinator():
    """Coordinator 不包含 C Stage: Crystallize 邏輯——只在 pipeline.py 中有。"""
    coord_path = Path("nexus/engine/coordinator.py")
    if not coord_path.exists():
        coord_path = Path(__file__).parent.parent / "nexus/engine/coordinator.py"
    content = coord_path.read_text()
    assert "# --- C Stage: Crystallize ---" not in content
    # Pipeline 應含該標記
    pipeline_path = Path("nexus/engine/pipeline.py")
    if not pipeline_path.exists():
        pipeline_path = Path(__file__).parent.parent / "nexus/engine/pipeline.py"
    assert "# --- C Stage: Crystallize ---" in pipeline_path.read_text()
