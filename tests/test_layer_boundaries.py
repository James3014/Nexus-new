from pathlib import Path
import pytest
import re

def test_forbidden_imports():
    """🛡️ 確保底層 (core/services) 不會循環導入高層 (engine/app)"""
    core_dir = Path("nexus/core")
    for py_file in core_dir.glob("**/*.py"):
        content = py_file.read_text()
        # core 不應導入 engine
        assert "from nexus.engine" not in content
        assert "import nexus.engine" not in content
        # core 不應導入 app
        assert "from nexus.app" not in content
        assert "import nexus.app" not in content

def test_engine_layer_rules():
    """⚙️ engine 可以導入 core 和 services，但不能導入 app"""
    engine_dir = Path("nexus/engine")
    for py_file in engine_dir.glob("**/*.py"):
        content = py_file.read_text()
        assert "from nexus.app" not in content
        assert "import nexus.app" not in content


def test_core_event_modules_are_compatibility_facades():
    """🧱 core 事件入口僅保留 façade，實作必須在 nexus/events。"""
    core_event_bus = Path("nexus/core/event_bus.py").read_text(encoding="utf-8")
    core_events = Path("nexus/core/events.py").read_text(encoding="utf-8")

    assert "from nexus.events.transport import NexusEventBus" in core_event_bus
    assert "class NexusEventBus" not in core_event_bus

    assert "from nexus.events.contracts import NexusEvent" in core_events
    assert "from nexus.events.store import EventStore" in core_events
    assert "@dataclass" not in core_events
