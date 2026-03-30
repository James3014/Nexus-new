import pytest
from unittest.mock import MagicMock
from nexus.core.action_brief import build_action_brief, ActionBrief

def test_build_action_brief_gemini_repair():
    """驗證 Gemini 修復任務的指令與上下文生成。"""
    decision = MagicMock()
    decision.action = "gemini_repair"
    decision.actor = "gemini"
    
    task = MagicMock()
    violations = [{"file": "app.py", "reason": "off-by-one", "suggestion": "check index"}]
    
    brief = build_action_brief(
        decision=decision,
        task=task,
        failure_summary="Test failure",
        files=["app.py"],
        violations=violations
    )
    
    assert brief.action == "gemini_repair"
    assert "Gemini repair" in brief.title
    assert "app.py" in brief.instructions
    assert "check index" in brief.instructions
    assert brief.context["target_files"] == "app.py"

def test_build_action_brief_codex_patch():
    """驗證 Codex 終極補丁任務的指令生成。"""
    decision = MagicMock()
    decision.action = "codex_patch"
    decision.actor = "codex"
    
    brief = build_action_brief(
        decision=decision,
        task=MagicMock(),
        failure_summary="Blocker",
        files=["main.py", "db.py"],
        violations=[]
    )
    
    assert brief.action == "codex_patch"
    assert "Codex definitive patch" in brief.title
    assert "main.py, db.py" in brief.context["target_files"]

def test_build_action_brief_felo_research():
    """驗證 Felo 外部研究任務的指令與上下文生成。"""
    decision = MagicMock()
    decision.action = "felo_research"
    decision.actor = "felo"
    
    task = MagicMock()
    task.language = "python"
    task.stacktrace_pattern = "Traceback..."
    
    brief = build_action_brief(
        decision=decision,
        task=task,
        failure_summary="Timeout error",
        files=[],
        violations=[{"suggestion": "Search for timeout docs"}]
    )
    
    assert brief.action == "felo_research"
    assert "Research" in brief.title
    assert brief.context["system"] == "python"
    assert "Search for timeout docs" in brief.context["tried"]
