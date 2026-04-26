import pytest
import shutil
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral
from nexus.core.skill_assembler import SkillAssembler
from nexus.core.criteria_builder import CriteriaBuilder

@pytest.fixture
def project_root(tmp_path):
    return tmp_path

def test_campaign_general_dynamic_dag(project_root):
    commander = CampaignGeneral(project_root)
    
    # 1. Refactor intent (Expected: 4 nodes with ImpactAnalysis)
    nodes_refactor = commander.decompose_intent("refactor the core storage")
    assert len(nodes_refactor) == 4
    assert any(n.node_id == "T1-XRAY" for n in nodes_refactor)
    
    # 2. Fix intent (Expected: 3 nodes)
    nodes_fix = commander.decompose_intent("fix the login bug")
    assert len(nodes_fix) == 3
    assert any(n.node_id == "T1-REPRO" for n in nodes_fix)
    
    # 3. Fallback (Expected: 2 nodes)
    nodes_fallback = commander.decompose_intent("just do it")
    assert len(nodes_fallback) >= 2
    assert any(n.node_id.startswith("T1-MIN-XRAY") or "MIN-XRAY" in n.node_id for n in nodes_fallback)

def test_skill_assembler_portability_and_determinism(project_root):
    assembler = SkillAssembler(project_root)
    intent = "implement bft consensus"
    
    # 1. Determinism
    s1 = assembler.assemble_new_skill(intent, "gap")
    s2 = assembler.assemble_new_skill(intent, "gap")
    assert s1 == s2
    assert "auto-gen-" in s1
    
    # 2. Metadata verification
    skill_md = project_root / "skills" / s1 / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "created_from_intent" in content
    assert "implement bft consensus" in content

def test_criteria_builder_gate_execution(project_root):
    cb = CriteriaBuilder(project_root)
    artifact_dir = project_root / "artifacts"
    
    # 1. Success case
    crit_ok = cb.build_custom_criteria("performance optimization")
    passed = cb.execute_criteria(crit_ok, artifact_dir)
    assert passed is True
    
    report_path = artifact_dir / "criteria_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["criteria_passed"] is True
    
    # 2. Failure case
    crit_fail = cb.build_custom_criteria("FAIL_TEST security")
    failed = cb.execute_criteria(crit_fail, artifact_dir)
    assert failed is False
    
    report_fail = json.loads(report_path.read_text())
    assert report_fail["criteria_passed"] is False
