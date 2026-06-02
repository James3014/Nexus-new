import pytest
from nexus.engine.artifact_manager import CRISPYArtifactManager

def test_artifact_template_generation():
    mgr = CRISPYArtifactManager()
    design_tmpl = mgr.generate_template("Design.md")
    assert "🎨 CRISPY: Design" in design_tmpl
    assert "核心取捨" in design_tmpl

def test_research_validation_fail_on_design():
    mgr = CRISPYArtifactManager()
    content = "The current flow is slow. We should implement a cache."
    valid, reason = mgr.validate_content("Research.md", content)
    assert valid is False
    assert "RESEARCH_CONTAINS_DESIGN" in reason

def test_research_validation_pass_on_facts():
    mgr = CRISPYArtifactManager()
    content = "The current flow consists of 3 steps: A, B, and C."
    valid, reason = mgr.validate_content("Research.md", content)
    assert valid is True

def test_design_validation_fail_on_plan_detail():
    mgr = CRISPYArtifactManager()
    content = "Decision: add a field at line 45 of core.py."
    valid, reason = mgr.validate_content("Design.md", content)
    assert valid is False
    assert "DESIGN_CONTAINS_PLAN_LEVEL_DETAIL" in reason
