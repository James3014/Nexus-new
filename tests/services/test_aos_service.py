import builtins
import importlib
import json
import sys
from pathlib import Path

import pytest

EXPECTED_STATUS = {
    "status": "OPERATIONAL",
    "aos_version": "145.2",
    "trust_score": 0.98,
    "governance": "ACTIVE",
}


@pytest.mark.parametrize("flag", ["aos", "aos_full"])
def test_aos_status_uses_service_env_prober_and_preserves_result(
    monkeypatch, tmp_path, capsys, flag
):
    from nexus.services.aos_service import AosService

    repo_root = Path(tmp_path)
    captured = {"transaction_roots": [], "probe_roots": []}

    class FakeTransactionManager:
        def __init__(self, root):
            captured["transaction_roots"].append(root)

    class FakeEnvProber:
        def __init__(self, root):
            captured["probe_roots"].append(root)

    monkeypatch.setattr(
        "nexus.core.engine.nexus_transaction.TransactionManager",
        FakeTransactionManager,
    )
    monkeypatch.setattr("nexus.services.nexus_probe.EnvProber", FakeEnvProber)

    result = AosService(repo_root).get_status(**{flag: True})
    output = capsys.readouterr().out

    assert result == EXPECTED_STATUS
    assert captured == {
        "transaction_roots": [repo_root],
        "probe_roots": [repo_root],
    }
    expected_lines = [
        "",
        "🛡️ [Nexus:AOS] Governance Verification (v23 Hardened)",
        "-" * 65,
        "🟢 P0 TransactionManager: ACTIVE",
        "🟢 P1 EnvProber: EXCELLENT",
        "🟢 P2 Conflict Guard: SAFE",
        "🟢 P3 Tool Lockdown: INSTITUTIONALIZED",
    ]
    if flag == "aos_full":
        expected_lines.append("🟢 P4 Swarm Fortress: 0 POLLUTION")
    assert output == "\n".join(expected_lines) + "\n" + json.dumps(EXPECTED_STATUS, indent=2) + "\n"


def test_aos_status_defaults_preserve_result_without_aos_dependencies(
    monkeypatch, tmp_path, capsys
):
    from nexus.services.aos_service import AosService

    def fail_constructor(*args, **kwargs):
        raise AssertionError("AOS dependencies should not be constructed")

    monkeypatch.setattr("nexus.core.engine.nexus_transaction.TransactionManager", fail_constructor)
    monkeypatch.setattr("nexus.services.nexus_probe.EnvProber", fail_constructor)

    assert AosService(Path(tmp_path)).get_status() == EXPECTED_STATUS
    assert capsys.readouterr().out == json.dumps(EXPECTED_STATUS, indent=2) + "\n"


def test_global_status_returns_early_without_constructing_aos_dependencies(
    monkeypatch, tmp_path, capsys
):
    imported_aos_dependencies = []
    real_import = builtins.__import__

    def track_import(name, *args, **kwargs):
        if name in {
            "nexus.core.engine.nexus_transaction",
            "nexus.services.nexus_probe",
        }:
            imported_aos_dependencies.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", track_import)
    monkeypatch.delitem(sys.modules, "nexus.services.aos_service", raising=False)
    AosService = importlib.import_module("nexus.services.aos_service").AosService

    assert AosService(Path(tmp_path)).get_status(global_view=True) == {
        "nodes": 10,
        "mode": "federated",
    }
    assert imported_aos_dependencies == []
    assert capsys.readouterr().out == "\n🌌 [Nexus Swarm] Federation Status (Nodes: 10)\n"
