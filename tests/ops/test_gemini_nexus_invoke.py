import os

from scripts.ops import gemini_nexus_invoke


def test_gemini_invoker_strips_nexus_runner_and_sandbox_env(monkeypatch):
    monkeypatch.setenv("NEXUS_RUNNER", "Gemini")
    monkeypatch.setenv("GEMINI_SANDBOX", "true")
    monkeypatch.setenv("NEXUS_KEEP_ME", "yes")

    env = gemini_nexus_invoke._gemini_subprocess_env()

    assert "NEXUS_RUNNER" not in env
    assert "GEMINI_SANDBOX" not in env
    assert env["NEXUS_KEEP_ME"] == "yes"
    assert os.environ["GEMINI_SANDBOX"] == "true"
