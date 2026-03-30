import pytest
from unittest.mock import MagicMock
from nexus.engine.phase_plugin import PhasePlugin, PhaseRegistry, PhaseResult, ErrorAction

class MockPlugin(PhasePlugin):
    def should_run(self, ctx):
        return True
    def execute(self, pipeline, ctx):
        return PhaseResult(status="success", mutations={})

def test_phase_registry_ordering():
    registry = PhaseRegistry()
    p1 = MockPlugin(name="P1", priority=200)
    p2 = MockPlugin(name="P2", priority=50)
    p3 = MockPlugin(name="P3", priority=100)
    
    registry.register(p1)
    registry.register(p2)
    registry.register(p3)
    
    ordered = registry.get_ordered_plugins()
    assert [p.name for p in ordered] == ["P2", "P3", "P1"]

def test_phase_registry_unregister():
    registry = PhaseRegistry()
    p1 = MockPlugin(name="P1")
    registry.register(p1)
    assert len(registry.get_ordered_plugins()) == 1
    
    registry.unregister("P1")
    assert len(registry.get_ordered_plugins()) == 0

def test_phase_plugin_default_error_action():
    plugin = MockPlugin(name="Test")
    action = plugin.on_error(None, Exception("fail"))
    assert action == ErrorAction.ABORT
