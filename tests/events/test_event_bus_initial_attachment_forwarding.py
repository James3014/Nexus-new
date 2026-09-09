from pathlib import Path

import pytest

from nexus.events.log_store import GenerationError, JsonlEventLogStore
from nexus.events.transport import NexusEventBus


@pytest.fixture(autouse=True)
def reset_event_bus():
    NexusEventBus._log_store = JsonlEventLogStore()
    NexusEventBus._event_log_path = None
    NexusEventBus._writer_factory = None
    yield
    NexusEventBus._log_store = JsonlEventLogStore()
    NexusEventBus._event_log_path = None
    NexusEventBus._writer_factory = None


def test_configure_forwards_initial_handle_unchanged(tmp_path: Path, monkeypatch):
    handle = object()
    seen = {}

    def configure(project_root, **kwargs):
        seen["project_root"] = project_root
        seen["initial_handle"] = kwargs["initial_handle"]
        return project_root / ".nexus/events", project_root / ".nexus/events/event_log.jsonl"

    monkeypatch.setattr(NexusEventBus._log_store, "configure", configure)
    monkeypatch.setattr(NexusEventBus._developer_feedback_store, "configure", lambda _root: None)

    NexusEventBus.configure(tmp_path, initial_handle=handle)

    assert seen == {"project_root": tmp_path, "initial_handle": handle}


def test_configure_still_rejects_invalid_initial_handle(tmp_path: Path):
    with pytest.raises(GenerationError, match="INITIAL_ATTACHMENT_HANDLE_INVALID"):
        NexusEventBus.configure(tmp_path, initial_handle=object())
