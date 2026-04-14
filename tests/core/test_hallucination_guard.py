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
    # restricted_claims + evidence_gap -> rejected
    response = "I have solved the problem."
    evidence = {"code_artifacts": []}
    analysis = guard.analyze(response, evidence)
    assert analysis["status"] == "REJECTED"
    assert "restricted_claims" in analysis["triggers"]


def test_self_grading_mild_risk():
    guard = HallucinationGuard()
    response = "I am 100% sure this works according to pytest."
    evidence = {"code_artifacts": []}
    analysis = guard.analyze(response, evidence)
    assert analysis["score"] >= 7.0
    assert "self_grading" in analysis["triggers"]


def test_unverified_status_claim_triggers_when_no_evidence():
    guard = HallucinationGuard()
    response = "Perplexity is outputting a complete summary now."
    analysis = guard.analyze(response, {"code_artifacts": [], "test_artifacts": []})
    assert analysis["status"] == "REJECTED"
    assert "unverified_status" in analysis["triggers"]


def test_contradiction_with_failed_artifacts_forces_rejected():
    guard = HallucinationGuard()
    response = "Task completed successfully. All tests passed."
    evidence = {
        "code_artifacts": ["nexus/core/hallucination_guard.py"],
        "test_artifacts": ["pytest output ... FAILED ..."],
        "command_artifacts": ['{"command":"uv run pytest -q","returncode": 1}'],
    }
    analysis = guard.analyze(response, evidence)
    assert analysis["status"] == "REJECTED"
    assert "contradiction_with_failed_artifacts" in analysis["triggers"]


def test_render_output():
    guard = HallucinationGuard()
    guard.analyze("Clean response", {"code_artifacts": ["a.py"]})
    output = guard.render()
    assert "## 🧠 幻覺指數" in output
    assert "🟢 安全" in output


def test_analyze_exposes_trigger_details():
    guard = HallucinationGuard()
    analysis = guard.analyze("I fixed this.", {"code_artifacts": []})
    assert isinstance(analysis.get("trigger_details"), list)
    assert analysis["trigger_details"]
