from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops import nexus_gateway_recovery_actuator_bootstrap as b


def _canonical_hash(value: dict[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


class FakeManager:
    def __init__(self, root: Path) -> None:
        self.GATEWAY_STATE_ROOT = root
        self.GATEWAY_STATE_ROOT.mkdir(mode=0o700)
        self.calls: list[str] = []
        self.live_calls = 0
        self.receipt = SimpleNamespace(
            receipt_id="receipt-v1",
            receipt_hash="a" * 64,
            request_id="request-v1",
            idempotency_fence="fence-v1",
            desired_manifest_id="desired-v1",
            predecessor_manifest_id="predecessor-v1",
        )
        self.request = SimpleNamespace(
            request_id="request-v1",
            request_hash="b" * 64,
            idempotency_fence="fence-v1",
            desired_manifest_id="desired-v1",
            predecessor_manifest_id="predecessor-v1",
        )
        self.materialization_request = SimpleNamespace(
            request_id="request-v1",
            request_hash="c" * 64,
            idempotency_fence="fence-v1",
            recovery_authority_id="receipt-v1",
            recovery_authority_hash="a" * 64,
        )
        self.materialization_effect_started = False
        self.preflight_effect_started = False
        self.preflight_readiness = ["TARGET_READY", "ROLLBACK_READY"]

    def canonical_hash(self, value):
        return _canonical_hash(dict(value))

    def _safe_store_path(self, path, **_kwargs):
        return Path(path)

    def _r1_materialize_value_store(self, path, data):
        path = Path(path)
        if path.exists():
            existing = path.read_bytes()
            if existing != data:
                raise RuntimeError("marker drift")
            return existing
        path.write_bytes(data)
        path.chmod(0o600)
        return data

    def _r1_refresh_fixed_authority_mirror(self):
        self.calls.append("refresh")
        return "1" * 40, "2" * 40

    def _r1_tracked_recovery_receipt(self, fresh_main):
        assert fresh_main == "1" * 40
        self.calls.append("tracked")
        return self.receipt, b"authority"

    def _r1_materialization_request_for_receipt(self, receipt):
        assert receipt is self.receipt
        self.calls.append("materialization-request")
        return self.materialization_request

    def derive_gateway_recovery_request(self, receipt):
        assert receipt is self.receipt
        self.calls.append("derive-request")
        return self.request

    def validate_recovery_request(self, request):
        assert request is self.request
        self.calls.append("validate-request")

    def gateway_recovery_materialize(self, request):
        assert request is self.materialization_request
        self.calls.append("materialize")
        return {
            "effect_started": self.materialization_effect_started,
            "fresh_main": "1" * 40,
            "fresh_main_tree": "2" * 40,
            "recovery_authority_id": self.receipt.receipt_id,
            "recovery_authority_hash": self.receipt.receipt_hash,
            "request_id": self.request.request_id,
            "idempotency_fence": self.request.idempotency_fence,
        }

    def gateway_recover(self, request):
        assert request is self.request
        self.calls.append("preflight")
        return {
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "idempotency_fence": request.idempotency_fence,
            "effect_started": self.preflight_effect_started,
            "result": "BLOCKED",
            "physical_observation": {"readiness": list(self.preflight_readiness)},
        }

    def _gateway_recover_live(self, request):
        assert request is self.request
        marker = self.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME
        assert marker.is_file()
        self.calls.append("live")
        self.live_calls += 1
        return {
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "idempotency_fence": request.idempotency_fence,
            "effect_started": True,
            "result": "VERIFIED",
        }

    def advance_generation(self) -> None:
        self.receipt = SimpleNamespace(
            receipt_id="receipt-v2",
            receipt_hash="d" * 64,
            request_id="request-v2",
            idempotency_fence="fence-v2",
            desired_manifest_id="desired-v2",
            predecessor_manifest_id="predecessor-v2",
        )
        self.request = SimpleNamespace(
            request_id="request-v2",
            request_hash="e" * 64,
            idempotency_fence="fence-v2",
            desired_manifest_id="desired-v2",
            predecessor_manifest_id="predecessor-v2",
        )
        self.materialization_request = SimpleNamespace(
            request_id="request-v2",
            request_hash="f" * 64,
            idempotency_fence="fence-v2",
            recovery_authority_id="receipt-v2",
            recovery_authority_hash="d" * 64,
        )


def test_effect_runs_only_after_effect_free_readiness_and_consumption(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")

    result = b._run_bootstrap(manager)

    assert result["status"] == "VERIFIED"
    assert manager.calls == [
        "refresh",
        "tracked",
        "materialization-request",
        "derive-request",
        "validate-request",
        "materialize",
        "preflight",
        "live",
    ]
    marker = json.loads((manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME).read_text())
    assert marker["recovery_authority_id"] == "receipt-v1"
    assert marker["request_id"] == "request-v1"
    assert marker["effect_started_at_marker"] is False
    assert marker["consumption_hash"] == _canonical_hash({
        key: value for key, value in marker.items() if key != "consumption_hash"
    })


@pytest.mark.parametrize(
    ("materialization_effect_started", "preflight_effect_started", "readiness"),
    [
        (True, False, ["TARGET_READY", "ROLLBACK_READY"]),
        (False, True, ["TARGET_READY", "ROLLBACK_READY"]),
        (False, False, ["TARGET_READY"]),
    ],
)
def test_non_effect_free_or_incomplete_readiness_blocks_before_marker_and_live(
    tmp_path,
    materialization_effect_started,
    preflight_effect_started,
    readiness,
):
    manager = FakeManager(tmp_path / "gateway-direct")
    manager.materialization_effect_started = materialization_effect_started
    manager.preflight_effect_started = preflight_effect_started
    manager.preflight_readiness = readiness

    with pytest.raises(b.BootstrapError):
        b._run_bootstrap(manager)

    assert not (manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME).exists()
    assert manager.live_calls == 0


def test_same_generation_replay_uses_same_live_request_for_manager_reconciliation(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")

    first = b._run_bootstrap(manager)
    second = b._run_bootstrap(manager)

    assert first["request_id"] == second["request_id"] == "request-v1"
    assert manager.live_calls == 2


def test_different_generation_is_rejected_before_materialize_preflight_or_live(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    b._run_bootstrap(manager)
    before = list(manager.calls)
    manager.advance_generation()

    with pytest.raises(b.BootstrapError, match="DIFFERENT_RECOVERY_GENERATION_FORBIDDEN"):
        b._run_bootstrap(manager)

    assert manager.calls[len(before) :] == [
        "refresh",
        "tracked",
        "materialization-request",
        "derive-request",
        "validate-request",
    ]
    assert manager.live_calls == 1


def test_main_rejects_all_caller_arguments(monkeypatch, capsys):
    monkeypatch.setattr(b, "run_bootstrap", lambda: pytest.fail("effect path reached"))

    assert b.main(["--target", "anything"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "reason": "CALLER_ARGUMENTS_FORBIDDEN",
        "status": "BLOCKED",
    }
