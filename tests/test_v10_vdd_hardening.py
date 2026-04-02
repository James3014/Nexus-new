from pathlib import Path
"""Unit tests for V3 VDD Hardening features (Embedding versioning, EventBus, Sandbox)"""
import tempfile
import json

from nexus.learning.embedding_cache import EmbeddingCache
from nexus.core.event_bus import NexusEventBus
from nexus.health.sandbox import SpeculativeSandbox


def test_embedding_cache_versioning():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        
        # Simulate Old Version Cache
        old_data = {"_model_version": "old-model-v1", "skill_test": [0.1, 0.2]}
        cache_file.write_text(json.dumps(old_data), encoding="utf-8")
        
        # Load Cache
        cache = EmbeddingCache(cache_file)
        
        # Expect the constructor to blow away the old version and re-init
        assert cache.model_version == EmbeddingCache.CURRENT_MODEL_VERSION
        assert "skill_test" not in cache.data


def test_event_bus_injection_and_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Configure EventBus
        NexusEventBus.configure(root)
        
        # Test signal injection
        NexusEventBus.inject_signal("test_signal", {"data": 123})
        
        # Drain signals
        signals = NexusEventBus.drain_signals("test_signal")
        assert len(signals) == 1
        assert signals[0]["payload"]["data"] == 123
        assert signals[0]["signal_type"] == "test_signal"


def test_sandbox_report_property():
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = SpeculativeSandbox(Path(tmpdir), mode="tmpdir")
        report = sandbox.sandbox_report
        assert report["sandbox_mode"] == "tmpdir"
        assert "docker_available" in report
        assert "source_root" in report
