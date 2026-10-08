"""One-shot bootstrap into the existing Nexus-owned Gateway recovery manager.

This bridge exists only for the self-bootstrap seam where the loaded Gateway is
too stale to expose the typed recovery tools that current source already owns.
It does not own recovery authority, request derivation, materialization,
preflight, the recovery ledger, launchd effects, rollback, or postflight.

The bridge accepts no caller-selected target, request, path, service, PID, or
plist. It derives one tracked recovery generation from the fixed manager,
requires the effect-free TARGET_READY + ROLLBACK_READY checkpoint, commits one
immutable bootstrap-consumption fence, then delegates the sole possible host
effect to the manager-local live recovery seam. A later different recovery
generation is rejected so subsequent recovery must use the normal Nexus-owned
MCP surface after bootstrap.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANAGER_MODULE = "scripts.ops.mcp_gateway_durable"
CONSUMPTION_FILENAME = "recovery-actuator-bootstrap-consumed.json"
CONSUMPTION_SCHEMA = "nexus.gateway.recovery_actuator_bootstrap_consumption.v1"
RESULT_SCHEMA = "nexus.gateway.recovery_actuator_bootstrap_result.v1"
_REQUIRED_READINESS = ["TARGET_READY", "ROLLBACK_READY"]


class BootstrapError(RuntimeError):
    """Fail-closed bootstrap contract error."""


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if not callable(dump):
        raise BootstrapError("MANAGER_RESULT_INVALID")
    try:
        payload = dump(mode="json")
    except TypeError:
        payload = dump()
    if not isinstance(payload, Mapping):
        raise BootstrapError("MANAGER_RESULT_INVALID")
    return dict(payload)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapError("BOOTSTRAP_CONSUMPTION_DUPLICATE_KEY")
        result[key] = value
    return result


def _manager() -> Any:
    return importlib.import_module(MANAGER_MODULE)


def _consumption_path(manager: Any) -> Path:
    path = Path(manager.GATEWAY_STATE_ROOT) / CONSUMPTION_FILENAME
    return Path(manager._safe_store_path(path, leaf_mode=0o600, create=True))


def _load_consumption(manager: Any) -> dict[str, Any] | None:
    path = _consumption_path(manager)
    if not path.exists():
        return None
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_MALFORMED") from exc
    if not isinstance(payload, dict) or payload.get("schema") != CONSUMPTION_SCHEMA:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_SCHEMA_INVALID")
    supplied_hash = payload.get("consumption_hash")
    if not isinstance(supplied_hash, str):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_HASH_INVALID")
    unsigned = dict(payload)
    unsigned.pop("consumption_hash", None)
    if manager.canonical_hash(unsigned) != supplied_hash:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_HASH_MISMATCH")
    return payload


def _generation_fields(
    receipt: Any,
    request: Any,
    materialization_request: Any,
) -> dict[str, Any]:
    return {
        "recovery_authority_id": receipt.receipt_id,
        "recovery_authority_hash": receipt.receipt_hash,
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "desired_manifest_id": request.desired_manifest_id,
        "predecessor_manifest_id": request.predecessor_manifest_id,
        "materialization_request_hash": materialization_request.request_hash,
    }


def _assert_same_generation(
    marker: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> None:
    if any(marker.get(key) != value for key, value in generation.items()):
        raise BootstrapError("DIFFERENT_RECOVERY_GENERATION_FORBIDDEN")


def _assert_materialization(
    payload: Mapping[str, Any],
    *,
    receipt: Any,
    request: Any,
) -> None:
    if payload.get("effect_started") is not False:
        raise BootstrapError("MATERIALIZATION_MUST_BE_EFFECT_FREE")
    expected = {
        "recovery_authority_id": receipt.receipt_id,
        "recovery_authority_hash": receipt.receipt_hash,
        "request_id": request.request_id,
        "idempotency_fence": request.idempotency_fence,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise BootstrapError("MATERIALIZATION_IDENTITY_MISMATCH")


def _assert_preflight(payload: Mapping[str, Any], *, request: Any) -> None:
    if payload.get("effect_started") is not False:
        raise BootstrapError("PREFLIGHT_MUST_BE_EFFECT_FREE")
    if payload.get("result") != "BLOCKED":
        raise BootstrapError("PREFLIGHT_RESULT_INVALID")
    if (
        payload.get("request_id") != request.request_id
        or payload.get("request_hash") != request.request_hash
        or payload.get("idempotency_fence") != request.idempotency_fence
    ):
        raise BootstrapError("PREFLIGHT_REQUEST_IDENTITY_MISMATCH")
    observation = payload.get("physical_observation")
    if not isinstance(observation, Mapping):
        raise BootstrapError("PREFLIGHT_PHYSICAL_OBSERVATION_MISSING")
    if observation.get("readiness") != _REQUIRED_READINESS:
        raise BootstrapError("RECOVERY_NOT_EFFECT_FREE_READY")


def _build_consumption(
    manager: Any,
    *,
    generation: Mapping[str, Any],
    fresh_main: str,
    fresh_tree: str,
    materialization: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "schema": CONSUMPTION_SCHEMA,
        **dict(generation),
        "fresh_main_at_consumption": fresh_main,
        "fresh_main_tree_at_consumption": fresh_tree,
        "materialization_sha256": manager.canonical_hash(dict(materialization)),
        "preflight_sha256": manager.canonical_hash(dict(preflight)),
        "effect_started_at_marker": False,
    }
    values["consumption_hash"] = manager.canonical_hash(values)
    return values


def _persist_consumption(manager: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    written = manager._r1_materialize_value_store(_consumption_path(manager), raw)
    if bytes(written) != raw:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_WRITE_MISMATCH")
    readback = _load_consumption(manager)
    if readback != dict(payload):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_READBACK_MISMATCH")
    return readback


def _run_bootstrap(manager: Any) -> dict[str, Any]:
    fresh_main, fresh_tree = manager._r1_refresh_fixed_authority_mirror()
    receipt, _authority_bytes = manager._r1_tracked_recovery_receipt(fresh_main)
    materialization_request = manager._r1_materialization_request_for_receipt(receipt)
    request = manager.derive_gateway_recovery_request(receipt)
    manager.validate_recovery_request(request)

    generation = _generation_fields(receipt, request, materialization_request)
    existing = _load_consumption(manager)
    if existing is not None:
        _assert_same_generation(existing, generation)

    materialization = _dump(manager.gateway_recovery_materialize(materialization_request))
    _assert_materialization(materialization, receipt=receipt, request=request)

    preflight = _dump(manager.gateway_recover(request))
    _assert_preflight(preflight, request=request)

    if existing is None:
        marker = _persist_consumption(
            manager,
            _build_consumption(
                manager,
                generation=generation,
                fresh_main=fresh_main,
                fresh_tree=fresh_tree,
                materialization=materialization,
                preflight=preflight,
            ),
        )
    else:
        marker = existing

    recovery = _dump(manager._gateway_recover_live(request))
    if (
        recovery.get("request_id") != request.request_id
        or recovery.get("request_hash") != request.request_hash
        or recovery.get("idempotency_fence") != request.idempotency_fence
    ):
        raise BootstrapError("LIVE_RECOVERY_REQUEST_IDENTITY_MISMATCH")

    status = recovery.get("result")
    if not isinstance(status, str) or not status:
        raise BootstrapError("LIVE_RECOVERY_RESULT_INVALID")
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "recovery_authority_id": receipt.receipt_id,
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "bootstrap_consumption_hash": marker["consumption_hash"],
        "manager_result": recovery,
    }


def run_bootstrap() -> dict[str, Any]:
    return _run_bootstrap(_manager())


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print(
            json.dumps(
                {"status": "BLOCKED", "reason": "CALLER_ARGUMENTS_FORBIDDEN"},
                sort_keys=True,
            )
        )
        return 2
    try:
        result = run_bootstrap()
    except Exception as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "reason": str(exc)},
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
