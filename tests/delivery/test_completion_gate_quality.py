import pytest
from pathlib import Path
from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest, TaskLevel, CompletionStatus

def test_completion_gate_fails_on_thin_content(tmp_path):
    art = tmp_path / "hollow.md"
    art.write_text("# Title Only", encoding="utf-8")
    
    req = CompletionRequest(
        task_name="test",
        task_level=TaskLevel.DOC,
        artifact_paths=[art],
        verification_commands=["true"],
        cwd=tmp_path
    )
    
    res = evaluate_completion(req)
    assert res.status == CompletionStatus.PARTIALLY_VERIFIED
    assert res.gate_passed is False
