from pathlib import Path

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


def test_core_governance_modules_are_compatibility_facades():
    """🧱 core 治理入口僅保留 façade，實作必須在 nexus/governance。"""
    core_capability_gate = Path("nexus/core/capability_gate.py").read_text(encoding="utf-8")
    core_evidence_guard = Path("nexus/core/evidence_guard.py").read_text(encoding="utf-8")
    core_hardened_validator = Path("nexus/core/hardened_validator.py").read_text(encoding="utf-8")

    assert "from nexus.governance.capability_gate import CapabilityGate, Phase" in core_capability_gate
    assert "class CapabilityGate" not in core_capability_gate

    assert "from nexus.governance.evidence_guard import NexusEvidenceGuard" in core_evidence_guard
    assert "class NexusEvidenceGuard" not in core_evidence_guard

    assert "from nexus.governance.hardened_validator import NexusHardenedValidator" in core_hardened_validator
    assert "class NexusHardenedValidator" not in core_hardened_validator


def test_runtime_modules_do_not_import_core_governance_shims():
    """🧱 非測試執行碼不得依賴 core 治理 shim，避免邊界回退。"""
    disallowed_imports = (
        "from nexus.core.capability_gate import",
        "from nexus.core.evidence_guard import",
        "from nexus.core.hardened_validator import",
    )
    shim_files = {
        Path("nexus/core/capability_gate.py"),
        Path("nexus/core/evidence_guard.py"),
        Path("nexus/core/hardened_validator.py"),
    }

    for py_file in Path("nexus").glob("**/*.py"):
        if py_file in shim_files:
            continue

        content = py_file.read_text(encoding="utf-8")
        for token in disallowed_imports:
            assert token not in content, f"{py_file} contains deprecated governance shim import: {token}"
