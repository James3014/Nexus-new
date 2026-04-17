import pytest
import json
import ast
from pathlib import Path
from nexus.core.skill_assembler import SkillAssembler

@pytest.fixture
def project_root(tmp_path):
    return tmp_path

def test_skill_jit_enhanced_interception(project_root):
    a = SkillAssembler(project_root)
    
    # 1. Malformed YAML
    s1 = "malformed-yaml"
    d1 = project_root / "skills" / s1
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text("---\nname: : : \n---", encoding="utf-8")
    assert a.verify_skill_jit(s1) is False
    
    # 2. Missing Contract Fields (description)
    s2 = "missing-desc"
    d2 = project_root / "skills" / s2
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text("---\nname: skill\nversion: 1.0.0\nmetadata: {}\n---", encoding="utf-8")
    assert a.verify_skill_jit(s2) is False
    
    # 3. AST Risk (os.system)
    s3 = "ast-risk"
    d3 = project_root / "skills" / s3
    (d3 / "scripts").mkdir(parents=True)
    (d3 / "SKILL.md").write_text("---\nname: risky\ndescription: risky\nversion: 1.0.0\nmetadata: {}\n---", encoding="utf-8")
    (d3 / "scripts" / "payload.py").write_text("import os\nos.system('rm -rf /')")
    assert a.verify_skill_jit(s3) is False
    
    # 4. Valid Skill
    s4 = "valid-skill"
    d4 = project_root / "skills" / s4
    (d4 / "scripts").mkdir(parents=True)
    (d4 / "SKILL.md").write_text("---\nname: valid\ndescription: valid\nversion: 1.0.0\nmetadata: {created_at: 'now'}\n---", encoding="utf-8")
    assert a.verify_skill_jit(s4) is True
