import pytest
import json
import yaml
from pathlib import Path
from nexus.services.prompt_builder import PromptBuilder

@pytest.fixture
def builder(tmp_path):
    """準備測試用的 PromptBuilder。"""
    project_root = tmp_path / "nexus_root"
    project_root.mkdir()
    return PromptBuilder(str(project_root))

def test_prompt_builder_basic_system(builder):
    """驗證系統 Prompt 的生成，應包含憲法限制與安全規制。"""
    prompt = builder.build_system_prompt("repair")
    assert "[Nexus v9 Constitution]" in prompt
    assert "Phase: repair" in prompt
    assert "Logic Guard" in prompt.lower() or "safety guards" in prompt.lower()

def test_prompt_builder_task_with_lessons(builder, tmp_path):
    """驗證任務 Prompt 是否能正確注入相關的經驗結晶 (Lessons)。"""
    # 建立模擬的經驗結晶檔案
    lesson_file = builder.lesson_path
    lesson_file.parent.mkdir(parents=True, exist_ok=True)
    with open(lesson_file, "w") as f:
        f.write(json.dumps({"signature": "bug1", "cause": "off-by-one", "lesson": "Check indices."}) + "\n")
    
    prompt = builder.build_task_prompt("bug1 fix", "Context info")
    assert "Check indices." in prompt
    assert "Context info" in prompt

def test_prompt_builder_full_payload(builder):
    """驗證完整 Payload 的組裝流程。"""
    diff = "--- a/old.py\n+++ b/old.py"
    payload = builder.build_full_payload("repair", "fix bug", diff)
    assert "[Nexus v9 Constitution]" in payload
    assert "[Code Diff / State]" in payload
    assert "--- a/old.py" in payload
