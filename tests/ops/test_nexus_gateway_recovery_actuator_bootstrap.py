from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops import mcp_gateway_durable as real_manager
from scripts.ops import nexus_gateway_recovery_actuator_bootstrap as b

_NOW = "2026-10-13T00:00:00Z"
_VERIFIED_PATH = [
    "REQUESTED",
    "PREFLIGHTED",
    "TARGET_READY",
    "ROLLBACK_READY",
    "EFFECT_STARTED",
    "SERVICE_OBSERVED",
    "IDENTITY_VERIFIED",
    "CLIENT_BOUND",
    "VERIFIED",
]


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
        self.receipt.expires_at = "2026-10-20T00:00:00Z"
        self.materialization_effect_started = False
        self.preflight_effect_started = False
        self.preflight_readiness = ["TARGET_READY", "ROLLBACK_READY"]
        self.in_gateway_process = False
        self.ledger_path = self.GATEWAY_STATE_ROOT / "ledger.jsonl"
        self.after_materialize: Callable[[], None] | None = None

    def canonical_hash(self, value):
        return _canonical_hash(dict(value))

    def _refuse_in_process_self_replacement(self):
        self.calls.append("in-process-guard")
        if self.in_gateway_process:
            raise real_manager.GatewayContractError(
                real_manager.R1_IN_PROCESS_SELF_REPLACEMENT_FORBIDDEN
            )

    def _current_observation_time(self):
        return _NOW

    def validate_recovery_authority(self, receipt, *, request=None, now=None):
        assert receipt is self.receipt
        assert request is self.request
        if not now or receipt.expires_at <= now:
            raise RuntimeError("R1 recovery authority stale")
        return receipt

    def GatewayLedger(self):
        return real_manager.GatewayLedger(self.ledger_path)

    def _r1_replace_value_store_cas(self, path, *, expected, target):
        path = Path(path)
        current = path.read_bytes()
        if current == target:
            return current
        if current != expected:
            raise RuntimeError("marker CAS conflict")
        path.write_bytes(target)
        return target

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
        if self.after_materialize is not None:
            self.after_materialize()
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

    def advance_generation(
        self,
        suffix: str = "2",
        *,
        expires_at: str = "2026-10-20T00:00:00Z",
        fence: str | None = None,
    ) -> None:
        receipt_hash = hashlib.sha256(f"receipt-{suffix}".encode()).hexdigest()
        fence = fence or f"fence-v{suffix}"
        self.receipt = SimpleNamespace(
            receipt_id=f"receipt-v{suffix}",
            receipt_hash=receipt_hash,
            request_id=f"request-v{suffix}",
            idempotency_fence=fence,
            desired_manifest_id=f"desired-v{suffix}",
            predecessor_manifest_id=f"predecessor-v{suffix}",
            expires_at=expires_at,
        )
        self.request = SimpleNamespace(
            request_id=f"request-v{suffix}",
            request_hash=hashlib.sha256(f"request-{suffix}".encode()).hexdigest(),
            idempotency_fence=fence,
            desired_manifest_id=f"desired-v{suffix}",
            predecessor_manifest_id=f"predecessor-v{suffix}",
        )
        self.materialization_request = SimpleNamespace(
            request_id=f"request-v{suffix}",
            request_hash=hashlib.sha256(f"materialize-{suffix}".encode()).hexdigest(),
            idempotency_fence=fence,
            recovery_authority_id=f"receipt-v{suffix}",
            recovery_authority_hash=receipt_hash,
        )

    def restore_generation(self, receipt, request, materialization_request) -> None:
        self.receipt = receipt
        self.request = request
        self.materialization_request = materialization_request


def _ledger_row(manager, marker, state, rows):
    row = {
        "schema": "nexus.gateway.ledger.v2",
        "request_id": marker["request_id"],
        "request_hash": marker["request_hash"],
        "state": state,
        "sequence": len(rows) + 1,
        "parent_hash": rows[-1]["record_hash"] if rows else "",
        "authority_schema": "nexus.gateway.durable_recovery_authority.v2",
        "receipt_id": marker["recovery_authority_id"],
        "receipt_hash": marker["recovery_authority_hash"],
        "card_sha256": "0" * 64,
        "accepted_source_merge": "1" * 40,
        "accepted_source_tree": "2" * 40,
        "final_manager_sha256": "3" * 64,
        "independent_acceptance_receipt_hash": "4" * 64,
        "source_set_sha256": "5" * 64,
        "desired_manifest_id": marker["desired_manifest_id"],
        "desired_manifest_hash": "6" * 64,
        "predecessor_manifest_id": marker["predecessor_manifest_id"],
        "predecessor_manifest_hash": "7" * 64,
        "source_bundle_evidence_hash": None if state == "REQUESTED" else "8" * 64,
        "operation": "gateway-recover",
        "effect_class": "GATEWAY_DURABLE_RECOVERY",
        "idempotency_fence": marker["idempotency_fence"],
        "pre_effect_identity": {},
        "observed_identity": {},
    }
    if state == "VERIFIED":
        row["observed_identity"] = {
            "outcome": {
                "request_id": marker["request_id"],
                "request_hash": marker["request_hash"],
                "idempotency_fence": marker["idempotency_fence"],
                "result": "VERIFIED",
            }
        }
    row["record_hash"] = real_manager._record_hash(row)
    return row


def _append_ledger(manager, marker, states):
    path = manager.ledger_path
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    for state in states:
        rows.append(_ledger_row(manager, marker, state, rows))
    payload = b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    path.write_bytes(payload)
    path.chmod(0o600)


def _current_marker_entry(manager):
    state = b._load_consumption_state(manager)
    assert state is not None
    return state[2][-1]


def _marker_bytes(manager):
    return (manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME).read_bytes()


def _consume_and_verify_v1(manager):
    b._run_bootstrap(manager)
    _append_ledger(manager, _current_marker_entry(manager), _VERIFIED_PATH)


def test_effect_runs_only_after_effect_free_readiness_and_consumption(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")

    result = b._run_bootstrap(manager)

    assert result["status"] == "VERIFIED"
    assert manager.calls == [
        "in-process-guard",
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


def test_different_generation_without_ledger_is_rejected_before_materialize_preflight_or_live(
    tmp_path,
):
    manager = FakeManager(tmp_path / "gateway-direct")
    b._run_bootstrap(manager)
    before = list(manager.calls)
    marker_before = _marker_bytes(manager)
    manager.advance_generation()

    with pytest.raises(
        b.BootstrapError,
        match="DIFFERENT_RECOVERY_GENERATION_FORBIDDEN:PREDECESSOR_LEDGER_MISSING",
    ):
        b._run_bootstrap(manager)

    assert manager.calls[len(before) :] == [
        "in-process-guard",
        "refresh",
        "tracked",
        "materialization-request",
        "derive-request",
        "validate-request",
    ]
    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


def test_next_generation_succeeds_after_verified_and_appends_marker_history(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    v1_marker = json.loads(_marker_bytes(manager))
    manager.advance_generation("2")

    result = b._run_bootstrap(manager)

    assert result["status"] == "VERIFIED"
    assert result["request_id"] == "request-v2"
    assert manager.live_calls == 2
    assert manager.calls[-3:] == ["materialize", "preflight", "live"]
    envelope = json.loads(_marker_bytes(manager))
    assert envelope["schema"] == b.SUCCESSION_SCHEMA
    assert envelope["consumption_hash"] == _canonical_hash({
        key: value for key, value in envelope.items() if key != "consumption_hash"
    })
    first, second = envelope["generations"]
    assert first == v1_marker  # carried verbatim, never deleted or rewritten
    assert second["schema"] == b.SUCCESSION_ENTRY_SCHEMA
    assert second["request_id"] == "request-v2"
    assert second["idempotency_fence"] == "fence-v2"
    assert second["predecessor_consumption_hash"] == v1_marker["consumption_hash"]
    assert second["predecessor_request_id"] == "request-v1"
    assert second["predecessor_verified_ledger_sequence"] == len(_VERIFIED_PATH)
    assert second["effect_started_at_marker"] is False
    assert result["bootstrap_consumption_hash"] == second["consumption_hash"]

    # Same-generation replay of the successor keeps reconciling through the
    # manager with the same request and does not rewrite the marker.
    marker_after = _marker_bytes(manager)
    replay = b._run_bootstrap(manager)
    assert replay["request_id"] == "request-v2"
    assert manager.live_calls == 3
    assert _marker_bytes(manager) == marker_after

    # A third generation chains onto the verified second one.
    _append_ledger(manager, second, _VERIFIED_PATH)
    manager.advance_generation("3")
    b._run_bootstrap(manager)
    history = json.loads(_marker_bytes(manager))["generations"]
    assert [entry["request_id"] for entry in history] == [
        "request-v1",
        "request-v2",
        "request-v3",
    ]
    assert history[:2] == [first, second]
    assert history[2]["predecessor_consumption_hash"] == second["consumption_hash"]


@pytest.mark.parametrize(
    "states",
    [
        ["REQUESTED"],
        ["REQUESTED", "PREFLIGHTED", "TARGET_READY", "ROLLBACK_READY"],
        _VERIFIED_PATH[:5],  # EFFECT_STARTED: in flight
        _VERIFIED_PATH[:8],  # CLIENT_BOUND: in flight, not yet VERIFIED
        [*_VERIFIED_PATH[:5], "UNCERTAIN_EFFECT"],
        [*_VERIFIED_PATH[:5], "BLOCKED"],
        ["REQUESTED", "BLOCKED"],
        [*_VERIFIED_PATH[:5], "UNCERTAIN_EFFECT", "ROLLED_BACK"],
    ],
    ids=[
        "requested",
        "rollback-ready",
        "effect-started",
        "client-bound",
        "uncertain-effect",
        "blocked-after-effect",
        "blocked-pre-effect",
        "rolled-back",
    ],
)
def test_non_verified_predecessor_blocks_succession_before_any_effect(tmp_path, states):
    manager = FakeManager(tmp_path / "gateway-direct")
    b._run_bootstrap(manager)
    _append_ledger(manager, _current_marker_entry(manager), states)
    marker_before = _marker_bytes(manager)
    manager.advance_generation()
    before = len(manager.calls)

    with pytest.raises(
        b.BootstrapError,
        match=f"DIFFERENT_RECOVERY_GENERATION_FORBIDDEN:PREDECESSOR_NOT_VERIFIED:{states[-1]}$",
    ):
        b._run_bootstrap(manager)

    assert "materialize" not in manager.calls[before:]
    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


def test_corrupt_ledger_blocks_succession(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    raw = manager.ledger_path.read_bytes()
    manager.ledger_path.write_bytes(raw.replace(b'"VERIFIED"', b'"VERIFIEX"', 1))
    marker_before = _marker_bytes(manager)
    manager.advance_generation()

    with pytest.raises(
        b.BootstrapError,
        match="DIFFERENT_RECOVERY_GENERATION_FORBIDDEN:PREDECESSOR_LEDGER_CORRUPT",
    ):
        b._run_bootstrap(manager)

    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


def test_predecessor_absent_or_rebound_in_ledger_blocks_succession(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    b._run_bootstrap(manager)
    v1 = _current_marker_entry(manager)
    other = {**v1, "request_id": "other-request", "idempotency_fence": "other-fence"}
    _append_ledger(manager, other, _VERIFIED_PATH)
    manager.advance_generation()

    with pytest.raises(b.BootstrapError, match="PREDECESSOR_NOT_IN_LEDGER"):
        b._run_bootstrap(manager)

    manager.ledger_path.unlink()
    rebound = {**v1, "recovery_authority_hash": "9" * 64}
    _append_ledger(manager, rebound, _VERIFIED_PATH)
    with pytest.raises(b.BootstrapError, match="PREDECESSOR_LEDGER_BINDING_MISMATCH"):
        b._run_bootstrap(manager)
    assert manager.live_calls == 1


def test_replay_of_any_consumed_generation_is_rejected(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    v1_identity = (
        manager.receipt,
        manager.request,
        manager.materialization_request,
    )
    _consume_and_verify_v1(manager)
    manager.advance_generation("2")
    b._run_bootstrap(manager)
    _append_ledger(manager, _current_marker_entry(manager), _VERIFIED_PATH)
    marker_before = _marker_bytes(manager)

    # Exact replay of the superseded v1 generation.
    manager.restore_generation(*v1_identity)
    with pytest.raises(
        b.BootstrapError,
        match="DIFFERENT_RECOVERY_GENERATION_FORBIDDEN:CONSUMED_GENERATION_REPLAY",
    ):
        b._run_bootstrap(manager)

    # A "new" generation that reuses a consumed fence is also a replay.
    manager.advance_generation("3", fence="fence-v1")
    with pytest.raises(b.BootstrapError, match="CONSUMED_GENERATION_REPLAY"):
        b._run_bootstrap(manager)

    assert manager.live_calls == 2
    assert _marker_bytes(manager) == marker_before


def test_expired_successor_receipt_is_rejected_before_any_effect(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    marker_before = _marker_bytes(manager)
    manager.advance_generation(expires_at="2026-10-12T00:00:00Z")
    before = len(manager.calls)

    with pytest.raises(
        b.BootstrapError,
        match="DIFFERENT_RECOVERY_GENERATION_FORBIDDEN:SUCCESSOR_RECEIPT_INVALID_OR_EXPIRED",
    ):
        b._run_bootstrap(manager)

    assert "materialize" not in manager.calls[before:]
    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


def test_tampered_tracked_receipt_still_fails_before_succession(tmp_path, monkeypatch):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    marker_before = _marker_bytes(manager)
    manager.advance_generation()

    def tampered(_fresh_main):
        raise real_manager.GatewayContractError("R1 tracked recovery receipt hash mismatch")

    monkeypatch.setattr(manager, "_r1_tracked_recovery_receipt", tampered)
    with pytest.raises(real_manager.GatewayContractError, match="hash mismatch"):
        b._run_bootstrap(manager)
    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda env: env["generations"][0].update(request_id="forged"),
        lambda env: env["generations"].pop(0),
        lambda env: env["generations"][1].update(predecessor_consumption_hash="0" * 64),
        lambda env: env.update(schema="nexus.gateway.unknown"),
    ],
    ids=["entry-forged", "history-truncated", "chain-broken", "schema"],
)
def test_tampered_succession_marker_fails_closed(tmp_path, mutate):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    manager.advance_generation()
    b._run_bootstrap(manager)
    path = manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME
    envelope = json.loads(path.read_bytes())
    mutate(envelope)
    unsigned = {key: value for key, value in envelope.items() if key != "consumption_hash"}
    envelope["consumption_hash"] = _canonical_hash(unsigned)
    path.write_bytes(json.dumps(envelope, sort_keys=True).encode())
    before_live = manager.live_calls

    with pytest.raises(b.BootstrapError, match="BOOTSTRAP_CONSUMPTION_"):
        b._run_bootstrap(manager)
    assert manager.live_calls == before_live


def test_predecessor_is_reobserved_before_successor_commit(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    marker_before = _marker_bytes(manager)
    manager.advance_generation()

    def corrupt_ledger():
        manager.ledger_path.write_bytes(b"{}\n")

    manager.after_materialize = corrupt_ledger
    with pytest.raises(b.BootstrapError, match="PREDECESSOR_LEDGER_CORRUPT"):
        b._run_bootstrap(manager)
    assert manager.live_calls == 1
    assert _marker_bytes(manager) == marker_before


def test_concurrent_marker_change_fails_successor_commit_by_cas(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    _consume_and_verify_v1(manager)
    manager.advance_generation()
    path = manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME

    def concurrent_writer():
        path.write_bytes(path.read_bytes() + b" ")

    manager.after_materialize = concurrent_writer
    with pytest.raises(RuntimeError, match="CAS conflict"):
        b._run_bootstrap(manager)
    assert manager.live_calls == 1


def test_in_gateway_process_is_refused_before_any_consumption(tmp_path):
    manager = FakeManager(tmp_path / "gateway-direct")
    manager.in_gateway_process = True

    with pytest.raises(
        real_manager.GatewayContractError,
        match="R1_IN_PROCESS_SELF_REPLACEMENT_FORBIDDEN",
    ):
        b._run_bootstrap(manager)

    assert manager.calls == ["in-process-guard"]
    assert not (manager.GATEWAY_STATE_ROOT / b.CONSUMPTION_FILENAME).exists()
    assert manager.live_calls == 0


def test_main_rejects_all_caller_arguments(monkeypatch, capsys):
    monkeypatch.setattr(b, "run_bootstrap", lambda: pytest.fail("effect path reached"))

    assert b.main(["--target", "anything"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "reason": "CALLER_ARGUMENTS_FORBIDDEN",
        "status": "BLOCKED",
    }
