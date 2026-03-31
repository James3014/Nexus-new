import pytest
from nexus.core.capability_gate import CapabilityGate, Phase
from nexus.core.dependency_probe import DependencyProbe
from pathlib import Path

# --- 🧪 Capability Gate Tests ---

def test_capability_gate_plan_no_write():
    """核驗 Plan 階段是否正確隔離寫入工具"""
    gate = CapabilityGate()
    tools = gate.get_tools("P")
    assert "read_file" in tools
    assert "replace_file_content" not in tools
    assert "write_to_file" not in tools

def test_capability_gate_repair_has_write():
    """核驗 Repair 階段具備寫入能力"""
    gate = CapabilityGate()
    tools = gate.get_tools("R")
    assert "replace_file_content" in tools
    assert "multi_replace_file_content" in tools
    assert "write_to_file" in tools

def test_capability_gate_invalid_phase_fallback():
    """核驗不合法階段是否 Fallback 至 Plan"""
    gate = CapabilityGate()
    tools = gate.get_tools("UNKNOWN")
    assert "read_file" in tools
    assert "replace_file_content" not in tools

# --- 🧪 Dependency Probe Tests ---

def test_dependency_probe_direct_impact(tmp_path):
    """核驗依賴探針對直接影響範圍的掃描真值"""
    # 建立模擬工作區
    (tmp_path / "nexus" / "core").mkdir(parents=True)
    target = tmp_path / "nexus" / "core" / "swarm.py"
    target.write_text("def fn(): pass")
    
    dependent = tmp_path / "nexus" / "engine"
    dependent.mkdir(parents=True)
    (dependent / "orchestrator.py").write_text("from nexus.core.swarm import fn")
    
    probe = DependencyProbe(str(tmp_path))
    probe.build_index()
    
    impact = probe.full_impact("nexus/core/swarm.py")
    assert "nexus/engine/orchestrator.py" in impact["direct_dependents"]
    assert impact["risk_level"] != "LOW"

def test_dependency_probe_high_risk_rating(tmp_path):
    """核驗高風險評等邏輯 (5+ 依賴)"""
    (tmp_path / "core").mkdir()
    target = tmp_path / "core" / "base.py"
    target.write_text("class Base: pass")
    
    for i in range(6):
        (tmp_path / f"service_{i}.py").write_text("from core.base import Base")
    
    probe = DependencyProbe(str(tmp_path))
    probe.build_index()
    impact = probe.full_impact("core/base.py")
    assert impact["risk_level"] == "HIGH"
    assert impact["impact_count"] >= 6
