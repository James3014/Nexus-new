"""Governance test fixtures: the notifier must never speak or pop up under pytest."""

import pytest

from nexus.core.notifier import NexusNotifier


class NotifierRecorder:
    """Records notifier side-effect calls instead of executing say/osascript."""

    def __init__(self, real_voice, real_ui):
        self.voice = []
        self.ui = []
        self.real_voice = real_voice
        self.real_ui = real_ui


@pytest.fixture(autouse=True)
def notifier_calls(monkeypatch):
    rec = NotifierRecorder(NexusNotifier._voice_alert, NexusNotifier._system_ui_notify)
    monkeypatch.setattr(NexusNotifier, "_voice_alert", staticmethod(rec.voice.append))
    monkeypatch.setattr(
        NexusNotifier,
        "_system_ui_notify",
        staticmethod(lambda title, message: rec.ui.append((title, message))),
    )
    return rec
