from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.contracts.state_owner_transition import ReceiptState
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from scripts.ops import state_owner_transition as cli
from tests.contracts.test_state_owner_transition import _raw


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _receipt(self, operation: str):
        self.calls.append(operation)
        from nexus.contracts.state_owner_transition import TransitionReceipt

        return TransitionReceipt(
            "a" * 64, "tx", ReceiptState.PREFLIGHT_READY, False, False, False, False
        )

    def preflight(self, request):
        return self._receipt("preflight")

    def apply(self, request):
        return self._receipt("apply")

    def reconcile(self, request):
        return self._receipt("reconcile")


def _write_request(tmp_path: Path, operation: str = "PREFLIGHT") -> Path:
    raw = _raw()
    raw["operation"] = operation
    path = tmp_path / "request.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_cli_defaults_to_zero_write_preflight_even_for_apply_request(tmp_path, monkeypatch, capsys):
    fake = _FakeService()
    monkeypatch.setattr(cli, "build_source_owned_transition_service", lambda: fake)
    path = _write_request(tmp_path, "APPLY")

    assert cli.main(["--request", str(path)]) == 0
    assert fake.calls == ["preflight"]
    assert json.loads(capsys.readouterr().out)["state"] == "PREFLIGHT_READY"


def test_cli_requires_explicit_apply_for_apply_request(tmp_path, monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(cli, "build_source_owned_transition_service", lambda: fake)
    path = _write_request(tmp_path, "APPLY")

    assert cli.main(["--request", str(path), "--apply"]) == 0
    assert fake.calls == ["apply"]


def test_cli_reconcile_requires_explicit_reconcile_flag(tmp_path, monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(cli, "build_source_owned_transition_service", lambda: fake)
    path = _write_request(tmp_path, "RECONCILE")

    assert cli.main(["--request", str(path), "--reconcile"]) == 0
    assert fake.calls == ["reconcile"]


def test_cli_rejects_arbitrary_path_override(tmp_path):
    path = _write_request(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["--request", str(path), "--source-root", str(tmp_path)])


def test_gateway_ingress_uses_strict_request_and_source_owned_factory(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.build_source_owned_transition_service",
        lambda service: fake,
    )
    gateway = object.__new__(UnifiedMCPGateway)
    gateway.service = object()
    raw = _raw()
    result = gateway.writer_transition_ingress(raw)
    assert result["state"] == "PREFLIGHT_READY"
    assert fake.calls == ["preflight"]


def test_gateway_mcp_manifest_and_call_reach_closed_transition_ingress(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.build_source_owned_transition_service",
        lambda service: fake,
    )
    gateway = object.__new__(UnifiedMCPGateway)
    gateway.service = object()
    listed = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {item["name"] for item in listed["result"]["tools"]}
    assert "nexus_writer_transition" in names
    called = gateway.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "nexus_writer_transition", "arguments": _raw()},
        }
    )
    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"]["state"] == "PREFLIGHT_READY"
    assert fake.calls == ["preflight"]


def test_gateway_ingress_rejects_fixture_or_unknown_fields(monkeypatch):
    gateway = object.__new__(UnifiedMCPGateway)
    raw = _raw()
    raw["fixture_authority"] = True
    with pytest.raises(ValueError, match="WRITER_TRANSITION_REQUEST_INVALID"):
        gateway.writer_transition_ingress(raw)
