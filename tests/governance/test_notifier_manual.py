from nexus.core.notifier import NexusNotifier


def test_manual_notifications(notifier_calls):
    # INFO: log only, no side effects
    NexusNotifier.notify("Test", "This is an INFO log.", level="INFO")
    assert notifier_calls.ui == []
    assert notifier_calls.voice == []

    # WARNING: UI notification only
    NexusNotifier.notify("Warning", "Detected staged changes!", level="WARNING")
    assert notifier_calls.ui == [("Warning", "Detected staged changes!")]
    assert notifier_calls.voice == []

    # CRITICAL: UI + voice
    NexusNotifier.notify("CRITICAL", "Regression detected!", level="CRITICAL")
    assert notifier_calls.ui[-1] == ("CRITICAL", "Regression detected!")
    assert notifier_calls.voice == ["NEXUS CRITICAL 偵測到嚴重異常，請審核行動。"]


def _spy_subprocess(monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a))
    return calls


def test_real_side_effects_are_suppressed_under_pytest(notifier_calls, monkeypatch):
    calls = _spy_subprocess(monkeypatch)
    notifier_calls.real_voice("x")
    notifier_calls.real_ui("t", "m")
    assert calls == []


def test_silent_env_suppresses_side_effects(notifier_calls, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("NEXUS_NOTIFIER_SILENT", "1")
    calls = _spy_subprocess(monkeypatch)
    notifier_calls.real_voice("x")
    notifier_calls.real_ui("t", "m")
    assert calls == []


def test_production_critical_still_speaks(notifier_calls, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("NEXUS_NOTIFIER_SILENT", raising=False)
    calls = _spy_subprocess(monkeypatch)
    notifier_calls.real_voice("x")
    notifier_calls.real_ui("t", "m")
    assert len(calls) == 2
