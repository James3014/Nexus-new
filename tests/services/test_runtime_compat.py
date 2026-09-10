from __future__ import annotations


def test_runtime_compatibility_requires_installed_runtime():
    import importlib.util

    assert importlib.util.find_spec("nexus_runtime") is not None
    from nexus.services import runtime_compat

    assert runtime_compat.UnifiedRuntime is runtime_compat._RUNTIME.UnifiedRuntime
    assert runtime_compat.UnifiedRuntimeRequest is runtime_compat._RUNTIME.UnifiedRuntimeRequest


def test_mainchain_entry_uses_runtime_forwarder_source():
    from pathlib import Path

    source = Path("nexus/services/mainchain_entry.py").read_text(encoding="utf-8")
    assert "from nexus.services.runtime_compat import" in source
    assert "from nexus.services.unified_runtime import" not in source
