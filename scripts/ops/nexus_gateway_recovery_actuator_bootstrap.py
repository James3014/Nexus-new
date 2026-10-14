"""One-shot bootstrap into the existing Nexus-owned Gateway recovery manager.

This bridge exists only for the self-bootstrap seam where the loaded Gateway is
too stale to expose the typed recovery tools that current source already owns.
It does not own recovery authority, request derivation, materialization,
preflight, the recovery ledger, launchd effects, rollback, or postflight.

The bridge accepts no caller-selected target, request, path, service, PID, or
plist. It derives one tracked recovery generation from the fixed manager,
requires the effect-free TARGET_READY + ROLLBACK_READY checkpoint, commits one
immutable bootstrap-consumption fence, then delegates the sole possible host
effect to the manager-local live recovery seam.

Generation succession (#1940): a later, different recovery generation is
admitted only when the consumed generation reached terminal VERIFIED in the
durable Gateway ledger and the new tracked receipt is fresh, fully valid and
distinct (authority, request, request hash, fence and materialization request)
from every generation ever consumed.  In-flight, UNCERTAIN_EFFECT, BLOCKED or
otherwise non-VERIFIED predecessors, replay of any consumed generation, stale
receipts, and a missing or corrupt ledger all stay fail-closed.  Succession is
recorded by appending to the consumption marker's hash-chained history via
compare-and-swap; earlier entries are carried verbatim and never deleted.
The in-Gateway MCP path cannot perform the effect (the manager refuses
in-process self-replacement), so this out-of-process actuator is the R1 effect
caller.
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
SUCCESSION_SCHEMA = "nexus.gateway.recovery_actuator_bootstrap_consumption.v2"
SUCCESSION_ENTRY_SCHEMA = "nexus.gateway.recovery_actuator_bootstrap_succession_entry.v1"
RESULT_SCHEMA = "nexus.gateway.recovery_actuator_bootstrap_result.v1"
_REQUIRED_READINESS = ["TARGET_READY", "ROLLBACK_READY"]
_GENERATION_KEYS = (
    "recovery_authority_id",
    "recovery_authority_hash",
    "request_id",
    "request_hash",
    "idempotency_fence",
    "desired_manifest_id",
    "predecessor_manifest_id",
    "materialization_request_hash",
)
# Every consumed generation must differ from a successor in all of these.
_DISTINCT_GENERATION_KEYS = (
    "recovery_authority_id",
    "recovery_authority_hash",
    "request_id",
    "request_hash",
    "idempotency_fence",
    "materialization_request_hash",
)
_SUCCESSION_LINK_KEYS = (
    "predecessor_consumption_hash",
    "predecessor_request_id",
    "predecessor_verified_ledger_sequence",
    "predecessor_verified_ledger_record_hash",
)
_LEDGER_SCHEMA = "nexus.gateway.ledger.v2"
_LEDGER_BINDING = {
    "receipt_id": "recovery_authority_id",
    "receipt_hash": "recovery_authority_hash",
    "request_hash": "request_hash",
    "idempotency_fence": "idempotency_fence",
    "desired_manifest_id": "desired_manifest_id",
    "predecessor_manifest_id": "predecessor_manifest_id",
}
_SUCCESSION_FORBIDDEN = "DIFFERENT_RECOVERY_GENERATION_FORBIDDEN"


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


def _verify_self_hash(manager: Any, payload: Mapping[str, Any]) -> None:
    supplied_hash = payload.get("consumption_hash")
    if not isinstance(supplied_hash, str):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_HASH_INVALID")
    unsigned = dict(payload)
    unsigned.pop("consumption_hash", None)
    if manager.canonical_hash(unsigned) != supplied_hash:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_HASH_MISMATCH")


def _validate_entry(
    manager: Any,
    entry: Any,
    *,
    schema: str,
) -> dict[str, Any]:
    if not isinstance(entry, dict) or entry.get("schema") != schema:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_SCHEMA_INVALID")
    _verify_self_hash(manager, entry)
    if any(not isinstance(entry.get(key), str) or not entry.get(key) for key in _GENERATION_KEYS):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_GENERATION_INVALID")
    if entry.get("effect_started_at_marker") is not False:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_GENERATION_INVALID")
    return entry


def _consumption_history(
    manager: Any,
    payload: Any,
) -> list[dict[str, Any]]:
    """Return the validated, append-only list of consumed generations."""
    if isinstance(payload, dict) and payload.get("schema") == CONSUMPTION_SCHEMA:
        return [_validate_entry(manager, payload, schema=CONSUMPTION_SCHEMA)]
    if not isinstance(payload, dict) or payload.get("schema") != SUCCESSION_SCHEMA:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_SCHEMA_INVALID")
    if set(payload) != {"schema", "generations", "consumption_hash"}:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_SCHEMA_INVALID")
    _verify_self_hash(manager, payload)
    generations = payload.get("generations")
    if not isinstance(generations, list) or len(generations) < 2:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_HISTORY_INVALID")
    history = [_validate_entry(manager, generations[0], schema=CONSUMPTION_SCHEMA)]
    for entry in generations[1:]:
        current = _validate_entry(manager, entry, schema=SUCCESSION_ENTRY_SCHEMA)
        previous = history[-1]
        if (
            current.get("predecessor_consumption_hash") != previous["consumption_hash"]
            or current.get("predecessor_request_id") != previous["request_id"]
            or type(current.get("predecessor_verified_ledger_sequence")) is not int
            or not isinstance(current.get("predecessor_verified_ledger_record_hash"), str)
        ):
            raise BootstrapError("BOOTSTRAP_CONSUMPTION_HISTORY_CHAIN_BROKEN")
        history.append(current)
    for key in _DISTINCT_GENERATION_KEYS:
        values = [entry[key] for entry in history]
        if len(set(values)) != len(values):
            raise BootstrapError("BOOTSTRAP_CONSUMPTION_HISTORY_DUPLICATE_GENERATION")
    return history


def _load_consumption_state(
    manager: Any,
) -> tuple[bytes, dict[str, Any], list[dict[str, Any]]] | None:
    path = _consumption_path(manager)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, ValueError) as exc:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_MALFORMED") from exc
    history = _consumption_history(manager, payload)
    return raw, payload, history


def _load_consumption(manager: Any) -> dict[str, Any] | None:
    state = _load_consumption_state(manager)
    return None if state is None else state[1]


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


def _is_same_generation(
    marker: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> bool:
    return all(marker.get(key) == value for key, value in generation.items())


def _succession_refusal(reason: str) -> BootstrapError:
    return BootstrapError(f"{_SUCCESSION_FORBIDDEN}:{reason}")


def _assert_not_consumed(
    history: list[dict[str, Any]],
    generation: Mapping[str, Any],
) -> None:
    """Any overlap with a consumed generation is a replay, never a successor."""
    for entry in history:
        if any(entry[key] == generation[key] for key in _DISTINCT_GENERATION_KEYS):
            raise _succession_refusal("CONSUMED_GENERATION_REPLAY")


def _assert_successor_receipt_fresh(manager: Any, receipt: Any, request: Any) -> None:
    """Re-run the full contract validator with the manager clock (expiry)."""
    try:
        manager.validate_recovery_authority(
            receipt,
            request=request,
            now=manager._current_observation_time(),
        )
    except Exception as exc:
        raise _succession_refusal("SUCCESSOR_RECEIPT_INVALID_OR_EXPIRED") from exc


def _predecessor_verified_row(
    manager: Any,
    predecessor: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the consumed generation to be terminal VERIFIED in the ledger."""
    ledger = manager.GatewayLedger()
    path = Path(ledger.path)
    if path.is_symlink() or not path.is_file():
        raise _succession_refusal("PREDECESSOR_LEDGER_MISSING")
    try:
        rows = ledger.read()
    except Exception as exc:
        raise _succession_refusal("PREDECESSOR_LEDGER_CORRUPT") from exc
    if not rows:
        raise _succession_refusal("PREDECESSOR_LEDGER_MISSING")
    selected = [
        row
        for row in rows
        if row.get("schema") == _LEDGER_SCHEMA
        and row.get("request_id") == predecessor["request_id"]
    ]
    if not selected:
        raise _succession_refusal("PREDECESSOR_NOT_IN_LEDGER")
    for row in selected:
        if any(
            row.get(ledger_key) != predecessor[marker_key]
            for ledger_key, marker_key in _LEDGER_BINDING.items()
        ):
            raise _succession_refusal("PREDECESSOR_LEDGER_BINDING_MISMATCH")
    terminal = selected[-1]
    state = terminal.get("state")
    if state == "BLOCKED":
        # #1995 item 2a: an Owner reconcile record (the Owner's chat approval,
        # recorded by the manager) bound to this exact BLOCKED row lets exactly
        # the next generation succeed it.
        try:
            reconciled = manager._r1_owner_reconcile_matches(selected)
        except Exception as exc:
            raise _succession_refusal("PREDECESSOR_OWNER_RECONCILE_INVALID") from exc
        if reconciled:
            return dict(terminal)
    if state != "VERIFIED":
        raise _succession_refusal(f"PREDECESSOR_NOT_VERIFIED:{state}")
    observed = terminal.get("observed_identity")
    outcome = observed.get("outcome") if isinstance(observed, Mapping) else None
    if (
        not isinstance(outcome, Mapping)
        or outcome.get("result") != "VERIFIED"
        or outcome.get("request_id") != predecessor["request_id"]
        or outcome.get("request_hash") != predecessor["request_hash"]
        or outcome.get("idempotency_fence") != predecessor["idempotency_fence"]
    ):
        raise _succession_refusal("PREDECESSOR_VERIFIED_OUTCOME_INVALID")
    return dict(terminal)


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


def _build_succession_entry(
    manager: Any,
    *,
    generation: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    verified_row: Mapping[str, Any],
    fresh_main: str,
    fresh_tree: str,
    materialization: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    values = _build_consumption(
        manager,
        generation=generation,
        fresh_main=fresh_main,
        fresh_tree=fresh_tree,
        materialization=materialization,
        preflight=preflight,
    )
    values.pop("consumption_hash")
    values["schema"] = SUCCESSION_ENTRY_SCHEMA
    values["predecessor_consumption_hash"] = predecessor["consumption_hash"]
    values["predecessor_request_id"] = predecessor["request_id"]
    values["predecessor_verified_ledger_sequence"] = verified_row["sequence"]
    values["predecessor_verified_ledger_record_hash"] = verified_row["record_hash"]
    values["consumption_hash"] = manager.canonical_hash(values)
    return values


def _persist_succession(
    manager: Any,
    *,
    expected_raw: bytes,
    history: list[dict[str, Any]],
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one generation by compare-and-swap; prior entries stay verbatim."""
    envelope: dict[str, Any] = {
        "schema": SUCCESSION_SCHEMA,
        "generations": [*(dict(item) for item in history), dict(entry)],
    }
    envelope["consumption_hash"] = manager.canonical_hash(envelope)
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    written = manager._r1_replace_value_store_cas(
        _consumption_path(manager), expected=expected_raw, target=raw
    )
    if bytes(written) != raw:
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_WRITE_MISMATCH")
    readback = _load_consumption_state(manager)
    if readback is None or readback[1] != envelope or readback[2][-1] != dict(entry):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_READBACK_MISMATCH")
    return readback[2][-1]


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
    if readback is None or readback != dict(payload):
        raise BootstrapError("BOOTSTRAP_CONSUMPTION_READBACK_MISMATCH")
    return readback


def _run_bootstrap(manager: Any) -> dict[str, Any]:
    # Fail before any consumption or materialization if this process is the
    # Gateway that the effect would boot out (#1940).
    manager._refuse_in_process_self_replacement()
    fresh_main, fresh_tree = manager._r1_refresh_fixed_authority_mirror()
    receipt, _authority_bytes = manager._r1_tracked_recovery_receipt(fresh_main)
    materialization_request = manager._r1_materialization_request_for_receipt(receipt)
    request = manager.derive_gateway_recovery_request(receipt)
    manager.validate_recovery_request(request)

    generation = _generation_fields(receipt, request, materialization_request)
    state = _load_consumption_state(manager)
    existing: dict[str, Any] | None = None
    succession: tuple[bytes, list[dict[str, Any]]] | None = None
    if state is not None:
        raw, _payload, history = state
        current = history[-1]
        if _is_same_generation(current, generation):
            existing = current
        else:
            _assert_not_consumed(history, generation)
            _assert_successor_receipt_fresh(manager, receipt, request)
            _predecessor_verified_row(manager, current)
            succession = (raw, history)

    materialization = _dump(manager.gateway_recovery_materialize(materialization_request))
    _assert_materialization(materialization, receipt=receipt, request=request)

    preflight = _dump(manager.gateway_recover(request))
    _assert_preflight(preflight, request=request)

    if succession is not None:
        raw, history = succession
        # Re-observe immediately before committing the successor fence.
        _assert_successor_receipt_fresh(manager, receipt, request)
        verified_row = _predecessor_verified_row(manager, history[-1])
        marker = _persist_succession(
            manager,
            expected_raw=raw,
            history=history,
            entry=_build_succession_entry(
                manager,
                generation=generation,
                predecessor=history[-1],
                verified_row=verified_row,
                fresh_main=fresh_main,
                fresh_tree=fresh_tree,
                materialization=materialization,
                preflight=preflight,
            ),
        )
    elif existing is None:
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
