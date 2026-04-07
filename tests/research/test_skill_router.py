import pytest
from pathlib import Path
from nexus.research.skill_router import SkillRouter
from nexus.core.research.gear import ARCCycle

@pytest.fixture
def skill_router(tmp_path):
    """建立臨時技能目錄與 Router。"""
    skills_dir = tmp_path / "skills"
    scout_dir = skills_dir / "scout"
    scout_dir.mkdir(parents=True)
    
    with open(scout_dir / "SKILL.md", "w", encoding="utf-8") as f:
        f.write("# Scout Skill\nTest Instruction")
    
    return SkillRouter(skills_dir)

def test_skill_router_loading(skill_router):
    """驗證 SkillRouter 加載內容。"""
    content = skill_router.load_skill_content("P")
    assert "Scout Skill" in content
    
    # 未定義階段應返回 Placeholder
    placeholder = skill_router.load_skill_content("Z")
    assert "Placeholder" in placeholder

def test_arc_cycle_fallback():
    """驗證 ARCCycle 在無 Router 時的 Fallback 行為。"""
    cycle = ARCCycle(router=None)
    result = cycle.run("test-query")
    
    assert result["status"] == "SUCCESS"
    assert result["mode"] == "LegacyARC"
    assert "topic_init" in result["findings"]
    assert result["stages_executed"] == 5

def test_arc_cycle_with_router(skill_router):
    """驗證 ARCCycle 使用 Router 的標準流程。"""
    cycle = ARCCycle(router=skill_router)
    result = cycle.run("test-query")
    
    assert result["status"] == "SUCCESS"
    assert result["mode"] == "SkillAware"
    # 預設會執行 P -> X -> D -> R -> A -> C
    assert result["stages_executed"] == 6
    assert "P" in result["executed_list"]
    assert "C" in result["executed_list"]
    assert "Executed scout with skill rules." in result["findings"]["P"]
