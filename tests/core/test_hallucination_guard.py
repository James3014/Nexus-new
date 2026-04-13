import pytest
from nexus.core.hallucination_guard import HallucinationGuard

def test_safe_response():
    guard = HallucinationGuard()
    response = "The system is functioning normally. I have read the files."
    evidence = {"code_artifacts": ["main.py"]}
    analysis = guard.analyze(response, evidence)
    assert analysis["status"] == "VERIFIED"
    assert analysis["score"] == 0.0

def test_partial_risk_restricted_word():
    guard = HallucinationGuard()
    # 觸發 'solved' (+5) + 'evidence_gap' (+7) = 10 (REJECTED)
    response = "I have solved the problem."
    evidence = {"code_artifacts": []} # No artifacts
    analysis = guard.analyze(response, evidence)
    assert analysis["status"] == "REJECTED"
    assert "solved" in analysis["triggers"]

def test_self_grading_mild_risk():
    guard = HallucinationGuard()
    # 觸發 'evidence_gap' (+7) = 7 (REJECTED)
    response = "I am 100% sure this works according to pytest."
    evidence = {"code_artifacts": []}
    analysis = guard.analyze(response, evidence)
    assert analysis["score"] >= 6.0
    assert "self_grading" in analysis["triggers"]

def test_render_output():
    guard = HallucinationGuard()
    guard.analyze("Clean response", {"code_artifacts": ["a.py"]})
    output = guard.render()
    assert "## 🧠 幻覺指數" in output
    assert "🟢 安全" in output
