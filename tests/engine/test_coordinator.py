from pathlib import Path
import pytest
import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
from nexus.engine.coordinator import NexusEngine
from nexus.engine.config import EngineConfig

@pytest.fixture
def mock_config():
    return EngineConfig(
        project_root=Path("/tmp/nexus_test"),
        run_dir="/tmp/nexus_test/runs/test-run",
        fast_mode=True,
        audit_level="standard",
        silent=True
    )

@pytest.fixture
def mock_dependencies():
    return {
        "state_io": MagicMock(),
        "commander": MagicMock(),
        "router": MagicMock(),
        "reporter": MagicMock(),
        "accumulator": MagicMock(),
        "health_evaluator": MagicMock(),
        "research_policy": MagicMock(),
    }

def test_engine_init(mock_config, mock_dependencies):
    with patch("nexus.telemetry.otel_config.init_otel") as mock_otel:
        engine = NexusEngine(
            config=mock_config,
            **mock_dependencies
        )
        
        assert engine.project_root == mock_config.project_root
        assert engine.run_dir == Path(mock_config.run_dir)
        assert engine.state_io == mock_dependencies["state_io"]
        assert mock_otel.called

def test_engine_lazy_properties(mock_config, mock_dependencies):
    with patch("nexus.telemetry.otel_config.init_otel"):
        engine = NexusEngine(config=mock_config, **mock_dependencies)
        
        # Test Hub lazy loading
        hub = engine.hub
        assert hub is not None
        
        # Test MemoryService lazy loading
        with patch("nexus.services.memory.MemoryService") as mock_mem_cls:
            mem = engine.memory
            assert mock_mem_cls.called
            assert mem is not None

def test_run_bug_redirects_to_pipeline(mock_config, mock_dependencies):
    with patch("nexus.telemetry.otel_config.init_otel"):
        engine = NexusEngine(config=mock_config, **mock_dependencies)
        engine.pipeline = MagicMock()
        engine.pipeline.run.return_value = True
        
        res = engine.run_bug(bug_id="bug-123", desc="fix it")
        
        assert res is True
        assert engine.pipeline.run.called
        assert engine.reporter.log_trace.called

def test_run_feature_redirects_to_pipeline(mock_config, mock_dependencies):
    with patch("nexus.telemetry.otel_config.init_otel"):
        engine = NexusEngine(config=mock_config, **mock_dependencies)
        engine.pipeline = MagicMock()
        engine.pipeline.run.return_value = True
        
        res = engine.run_feature(task="build it")
        
        assert res is True
        assert engine.pipeline.run.called

def test_add_step_to_history(mock_config, mock_dependencies):
    with patch("nexus.telemetry.otel_config.init_otel"):
        engine = NexusEngine(config=mock_config, **mock_dependencies)
        mock_state = MagicMock()
        mock_state.steps_history = []
        
        engine._add_step_to_history(mock_state, "P", status="completed", summary="planned")
        
        assert len(mock_state.steps_history) == 1
        assert mock_state.steps_history[0].phase == "P"
        assert engine.state_io.save_global_state.called
