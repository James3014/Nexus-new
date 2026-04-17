import pytest
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral
from nexus.core.skill_assembler import SkillAssembler
from nexus.core.criteria_builder import CriteriaBuilder

@pytest.fixture
def project_root(tmp_path):
    return tmp_path

def test_l1_l7_full_chain_scenarios(project_root):
    # 初始化模組
    commander = CampaignGeneral(project_root)
    assembler = SkillAssembler(project_root)
    builder = CriteriaBuilder(project_root)
    
    scenarios = [
        "fix critical overflow bug in memory service",
        "implement new bft-aware consensus algorithm",
        "refactor core event bus for lower latency",
        "perform deep security audit for auth provider",
        "update technical documentation for api v3",
        "system-wide health check and service restart",
        "optimize database query performance",
        "add new feature for federated learning",
        "patch security vulnerability in websocket core",
        "rewrite login service logic",
        "migrate database schema to v4",
        "setup monitoring dashboard for production"
    ]
    
    trace_ids = []
    for i, intent in enumerate(scenarios):
        # 1. Intent Decompose (L4)
        nodes = commander.decompose_intent(intent, seed=i)
        assert len(nodes) >= 2
        
        # 2. Criteria Build (L2)
        for node in nodes:
            node.criteria = builder.build_custom_criteria(node.intent)
            
            # 3. Execution & Gate (L2)
            artifact_dir = project_root / f"artifacts/task_{i}_{node.node_id}"
            success = builder.execute_criteria(node.criteria, artifact_dir, trace_id=f"T-{i}")
            node.criteria_passed = success
            node.status = "SUCCESS" if success else "FAIL"
            trace_ids.append(f"T-{i}")

    # 4. Report Generation (L7)
    commander.generate_evolution_report(project_root / "reports", route_decision="NightShift")
    report_path = project_root / "reports/pipeline_evolution_report.json"
    assert report_path.exists()
    
    report = json.loads(report_path.read_text())
    assert len(report["dag_summary"]) > 0
    assert "trace_ids" in report
    assert len(report["trace_ids"]) == len(commander.campaign_map)

def test_regression_hardcoded_dag_protection(project_root):
    # 確保不同意圖不回傳相同的硬編碼 6 節點圖
    c = CampaignGeneral(project_root)
    n1 = c.decompose_intent("short task")
    n2 = c.decompose_intent("refactor the whole system core")
    assert len(n1) != len(n2)
    assert len(n1) == 2 # Fallback
    assert len(n2) == 4 # Refactor (Updated from 3 to 4)

def test_regression_skill_naming_stability(project_root):
    # 確保同意圖產生同技能名稱 (SHA256)
    a = SkillAssembler(project_root)
    intent = "implement bft"
    s1 = a.assemble_new_skill(intent, "gap")
    s2 = a.assemble_new_skill(intent, "gap")
    assert s1 == s2
    assert "auto-gen-" in s1

def test_regression_criteria_no_skip(project_root):
    # 確保 Criteria 執行後會生成報表且不被跳過
    cb = CriteriaBuilder(project_root)
    artifact_dir = project_root / "gate_test"
    cb.execute_criteria({"intent": "test", "required_tests": ["t1"]}, artifact_dir)
    assert (artifact_dir / "criteria_report.json").exists()

def test_skill_jit_bad_cases_interception(project_root):
    a = SkillAssembler(project_root)
    
    # 案例 1: 缺少 YAML Frontmatter
    s1 = "bad-fm"
    d1 = project_root / "skills" / s1
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text("just text", encoding="utf-8")
    assert a.verify_skill_jit(s1) is False
    
    # 案例 2: 缺少必填欄位 (name)
    s2 = "missing-name"
    d2 = project_root / "skills" / s2
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text("---\ndescription: hi\n---\nbody", encoding="utf-8")
    assert a.verify_skill_jit(s2) is False

    # 案例 3: YAML 格式錯誤
    s3 = "malformed-yaml"
    d3 = project_root / "skills" / s3
    d3.mkdir(parents=True)
    (d3 / "SKILL.md").write_text("---\nname: : : : \n---\nbody", encoding="utf-8")
    assert a.verify_skill_jit(s3) is False
