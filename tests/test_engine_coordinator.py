import sys
import types
import subprocess
from pathlib import Path

sys.modules.setdefault("lancedb", types.SimpleNamespace(connect=lambda *args, **kwargs: None))
sys.modules.setdefault(
    "redis",
    types.SimpleNamespace(Redis=lambda *args, **kwargs: types.SimpleNamespace(ping=lambda: True)),
)

from nexus.engine.coordinator import NexusEngine
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.services.predictor import Predictor
from nexus.core.state_contracts import NexusState
from nexus.core.context_hub import ContextHub
from unittest.mock import MagicMock, patch

def test_engine_initialization(tmp_path):
    """測試引擎初始化與目錄建立。"""
    engine = NexusEngine(project_root=tmp_path, silent=True)
    assert engine.project_root == tmp_path
    assert engine.run_dir.exists()
    assert engine.state_io is not None
    assert engine.commander is not None

def test_engine_predict_via_planner(tmp_path):
    """測試透過 PlannerPhaseHandler 執行的風險預判邏輯。"""
    predictor = Predictor()
    planner = PlannerPhaseHandler(project_root=tmp_path, run_dir=tmp_path, predictor=predictor)
    engine = NexusEngine(project_root=tmp_path, silent=True, phases={"P": planner})
    
    state = NexusState(task_id="test-001")
    
    # 測試 HTML 任務風險 (JS conflict)
    # 這裡模擬 planner.run 的調用，驗證 Predictor 被正確觸發
    res = planner.run(state, {"task": "Fix HTML and js issues", "domain": "frontend"})
    assert res["risk_score"] >= 0.3 # 0.3 for js
    assert "JS conflict risk" in str(res["risks"])
    
    # 測試高風險任務 (file read)
    res = planner.run(state, {"task": "read sensitive file", "domain": "core"})
    assert res["risk_score"] >= 0.8 # 0.8 for read/file
    assert "Browser sandbox risk" in str(res["risks"])


def test_context_hub_exposes_feature_pack(tmp_path):
    engine = NexusEngine(project_root=tmp_path, silent=True)
    pack = engine.hub.assemble_feature_pack(plan={"steps": ["s1"]})
    assert isinstance(pack, dict)
    assert "plan" in pack


def test_run_feature_compat_fallback_when_hub_missing_feature_pack(tmp_path):
    class LegacyHub:
        def make_pre_routing_decision(self, task_id, context=None):
            return {"external_needed": False}

        def record_crystal_lesson(self, *args, **kwargs):
            return None

    mock_router = MagicMock()
    mock_router.route_candidates.return_value = [{"skill_id": "self-healer", "score": 1.0}]
    mock_commander = MagicMock()
    mock_commander.hub = LegacyHub()

    engine = NexusEngine(
        project_root=tmp_path,
        silent=True,
        router=mock_router,
        commander=mock_commander,
        phases={"P": MagicMock(), "X": MagicMock(), "R": MagicMock()}
    )
    # Mock the pipeline directly to test compat shell logic
    engine.pipeline = MagicMock()
    engine.pipeline.run.return_value = True

    ok = engine.run_feature("compat fallback smoke", dry_run=True)
    assert ok is True


def test_run_feature_compat_fallback_when_hub_feature_pack_raises(tmp_path):
    class FlakyHub:
        def make_pre_routing_decision(self, task_id, context=None):
            return {"external_needed": False}

        def assemble_feature_pack(self, plan=None):
            raise RuntimeError("legacy hub mismatch")

        def record_crystal_lesson(self, *args, **kwargs):
            return None

    mock_router = MagicMock()
    mock_router.route_candidates.return_value = [{"skill_id": "self-healer", "score": 1.0}]
    mock_commander = MagicMock()
    mock_commander.hub = FlakyHub()

    engine = NexusEngine(
        project_root=tmp_path,
        silent=True,
        router=mock_router,
        commander=mock_commander,
        phases={"P": MagicMock(), "X": MagicMock(), "R": MagicMock()}
    )
    # Mock the pipeline directly to test compat shell logic
    engine.pipeline = MagicMock()
    engine.pipeline.run.return_value = True

    ok = engine.run_feature("compat fallback raise smoke", dry_run=True)
    assert ok is True


def test_execute_isolated_case_routes_through_command_service(tmp_path):
    engine = NexusEngine(project_root=tmp_path, silent=True)
    sub_engine = MagicMock()

    with patch("nexus.engine.coordinator.NexusCommandService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.execute_bug.return_value = True
        mock_service_cls.return_value = mock_service

        ok = engine._execute_isolated_case(
            sub_engine,
            case_type="bug",
            case_id="OFF-001",
            goal_desc="fix login callback",
            case_data={"goal": "fix login callback"},
        )

    assert ok is True
    mock_service_cls.assert_called_once_with(sub_engine)
    mock_service.execute_bug.assert_called_once_with(
        "fix login callback",
        delivery_mode="standard",
        bug_id="OFF-001",
        execution_context={
            "auto_repair_enabled": False,
            "benchmark_run": True,
            "benchmark_force_research": True,
            "benchmark_target_files": [],
        },
    )


def test_context_hub_disables_external_research_for_benchmark_run(tmp_path):
    hub = ContextHub(str(tmp_path), run_dir=str(tmp_path / ".nexus" / "runs" / "bench"))
    decision = hub.make_pre_routing_decision(
        "OFF-001",
        {"type": "bug", "benchmark_run": True},
    )

    assert decision["external_needed"] is False
    assert decision["mode"] == "benchmark"


def test_benchmark_fixture_mutates_and_restores(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True)

    target = tmp_path / "nexus" / "engine" / "phases"
    target.mkdir(parents=True)
    research_file = target / "research.py"
    original_text = "import json\nimport os\n"
    research_file.write_text(original_text, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    engine = NexusEngine(project_root=tmp_path, silent=True)
    fixture = engine._apply_benchmark_fixture(
        {
            "benchmark_fixture": {
                "file": "nexus/engine/phases/research.py",
                "target": "import os\n",
                "replacement": "",
            }
        }
    )

    assert fixture is not None
    assert research_file.read_text(encoding="utf-8") == "import json\n"

    engine._restore_benchmark_fixture(fixture)
    assert research_file.read_text(encoding="utf-8") == original_text
