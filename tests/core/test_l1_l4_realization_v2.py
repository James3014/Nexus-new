import pytest
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral, TaskNode, StrategicEnvelope
from nexus.core.skill_assembler import SkillAssembler
from nexus.core.criteria_builder import CriteriaBuilder

@pytest.fixture
def project_root(tmp_path):
    return tmp_path

# L4 Tests (4 units)
def test_dag_no_cycles(project_root):
    c = CampaignGeneral(project_root)
    nodes = c.decompose_intent("implement refactor security fix")
    assert c._has_cycle(nodes) is False

def test_dag_fallback_marking(project_root):
    c = CampaignGeneral(project_root)
    nodes = c.decompose_intent("unknown task")
    assert any("FALLBACK_USED" in n.envelope.global_constraints for n in nodes if n.envelope)

def test_dag_variance(project_root):
    c = CampaignGeneral(project_root)
    n1 = c.decompose_intent("fix bug")
    n2 = c.decompose_intent("implement feature")
    assert [n.node_id for n in n1] != [n.node_id for n in n2]

def test_dag_bursting_logic(project_root):
    c = CampaignGeneral(project_root)
    nodes = c.decompose_intent("core")
    node_id = nodes[0].node_id
    c.trigger_burst(node_id)
    assert node_id not in c.campaign_map
    assert f"{node_id}.1" in c.campaign_map

# L3 Tests (3 units)
def test_skill_jit_failure_capture(project_root):
    a = SkillAssembler(project_root)
    skill_name = "broken"
    skill_dir = project_root / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("broken")
    assert a.verify_skill_jit(skill_name) is False
    assert (skill_dir / "jit_failure.log").exists()

def test_skill_deterministic_naming(project_root):
    a = SkillAssembler(project_root)
    s1 = a.assemble_new_skill("intent A", "gap")
    s2 = a.assemble_new_skill("intent A", "gap")
    assert s1 == s2

def test_skill_metadata_integrity(project_root):
    a = SkillAssembler(project_root)
    s = a.assemble_new_skill("intent B", "reason B")
    content = (project_root / "skills" / s / "SKILL.md").read_text()
    assert "reason B" in content

# L2 Tests (3 units)
def test_criteria_repair_path_trigger(project_root):
    cb = CriteriaBuilder(project_root)
    artifact_dir = project_root / "artifacts"
    res = cb.execute_criteria({"intent": "fail_test", "required_tests": ["t1"]}, artifact_dir)
    assert res is False
    report = json.loads((artifact_dir / "criteria_report.json").read_text())
    assert report["requires_repair"] is True

def test_criteria_trace_id_propagation(project_root):
    cb = CriteriaBuilder(project_root)
    artifact_dir = project_root / "artifacts"
    cb.execute_criteria({"intent": "ok", "required_tests": ["t1"]}, artifact_dir, trace_id="T-100")
    report = json.loads((artifact_dir / "criteria_report.json").read_text())
    assert report["trace_id"] == "T-100"

def test_criteria_report_generation(project_root):
    cb = CriteriaBuilder(project_root)
    report_path = project_root / "report.json"
    cb.generate_criteria_report([{"criteria_passed": True}], report_path)
    assert report_path.exists()

# E2E Tests (2 units)
def test_e2e_flow_success(project_root):
    c = CampaignGeneral(project_root)
    nodes = c.decompose_intent("fix bug")
    for n in nodes:
        n.status = "SUCCESS"
        n.criteria_passed = True
    c.generate_evolution_report(project_root / "reports")
    assert (project_root / "reports" / "pipeline_evolution_report.json").exists()

def test_e2e_flow_partial(project_root):
    c = CampaignGeneral(project_root)
    nodes = c.decompose_intent("refactor")
    nodes[0].status = "SUCCESS"
    nodes[1].status = "FAIL"
    c.generate_evolution_report(project_root / "reports")
    report = json.loads((project_root / "reports" / "pipeline_evolution_report.json").read_text())
    assert report["execution_outcome"] == "PARTIAL"
