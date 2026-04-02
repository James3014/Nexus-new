from pathlib import Path
import pytest
from nexus.engine.config import EngineConfig

def test_engine_config_defaults():
    config = EngineConfig(project_root=Path("/tmp"))
    assert config.fast_mode is False
    assert config.audit_level == "normal"
    assert config.silent is False
    assert config.project_root == Path("/tmp")

def test_engine_config_custom_values():
    config = EngineConfig(
        project_root=Path("/tmp"),
        fast_mode=True,
        audit_level="strict",
        silent=True,
        run_dir="/tmp/run1"
    )
    assert config.fast_mode is True
    assert config.audit_level == "strict"
    assert config.run_dir == "/tmp/run1"

def test_engine_config_validation():
    # Test with invalid types if using pydantic, else simple tests
    config = EngineConfig(project_root="/tmp")
    # If using Pydantic, this might fail or auto-convert. 
    # Current engine.config uses dataclass, so it converts to Path in __init__
    assert config.project_root == "/tmp" 
