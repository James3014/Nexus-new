from nexus.engine.coordinator import NexusEngine
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.services.predictor import Predictor
from nexus.core.state_contracts import NexusState
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
    assert "proposed_plan" in pack


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
    )

    with patch("nexus.engine.coordinator.CodexLoopV2.run_review", return_value={"status": "APPROVED"}):
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
    )

    with patch("nexus.engine.coordinator.CodexLoopV2.run_review", return_value={"status": "APPROVED"}):
        ok = engine.run_feature("compat fallback raise smoke", dry_run=True)
    assert ok is True
