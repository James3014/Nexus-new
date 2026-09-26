from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

TOOL_EXPOSURE_RECEIPT_SCHEMA = "nexus.tool_exposure_receipt.v1"

ENFORCEMENT_MODES = frozenset(
    {
        "ENFORCED_NATIVE_PROVIDER",
        "ENFORCED_MANAGED_BRIDGE",
        "REQUEST_ONLY_NOT_ENFORCED",
        "NOT_OBSERVED",
        "NO_EXTERNAL_TOOL_SURFACE",
        "UNKNOWN",
    }
)

PHYSICALLY_ENFORCED_MODES = frozenset(
    {
        "ENFORCED_NATIVE_PROVIDER",
        "ENFORCED_MANAGED_BRIDGE",
    }
)

_EXPECTED_FIELDS = frozenset(
    {
        "schema",
        "operation_id",
        "attempt_id",
        "provider",
        "backend_id",
        "planner_decision_hash",
        "projection_hash",
        "enforcement_mode",
        "candidate_tools",
        "selected_tools",
        "actual_exposed_tools",
        "actual_exposed_tool_count",
        "authority_kind",
        "exposure_hash",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ToolExposureError(ValueError):
    """Base error for tool exposure contract violations."""


class ToolExposureWidenedError(ToolExposureError):
    """Raised when actual exposed tools exceed selected tools or ceiling."""


class ToolExposureIdentityError(ToolExposureError):
    """Raised when attempt, operation, or projection identity mismatches."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_hex64(value: Any, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or _SHA256_RE.fullmatch(text) is None:
        raise ToolExposureIdentityError(f"{field}_invalid")
    return text


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolExposureIdentityError(f"{field}_invalid")
    return value.strip()


def build_tool_exposure_receipt(
    *,
    operation_id: str,
    attempt_id: str,
    provider: str,
    backend_id: str,
    planner_decision_hash: str,
    projection_hash: str,
    enforcement_mode: str,
    candidate_tools: Sequence[str],
    selected_tools: Sequence[str],
    actual_exposed_tools: Sequence[str],
) -> dict[str, Any]:
    """Construct a canonical derived physical-exposure evidence record.

    This helper does not grant authority or prove that a physical producer
    actually exposed the supplied surface; that provenance must come from the
    bound provider/runtime path. Invariants:
    1. selected_tools <= candidate_tools
    2. actual_exposed_tools <= selected_tools
    3. enforcement_mode in ENFORCEMENT_MODES
    """
    op_id = _require_text(operation_id, "operation_id")
    att_id = _require_text(attempt_id, "attempt_id")
    prov = _require_text(provider, "provider")
    backend = _require_text(backend_id, "backend_id")
    dec_hash = _require_hex64(planner_decision_hash, "planner_decision_hash")
    proj_hash = _require_hex64(projection_hash, "projection_hash")

    if enforcement_mode not in ENFORCEMENT_MODES:
        raise ToolExposureError(f"enforcement_mode_invalid:{enforcement_mode}")

    candidates = tuple(sorted(set(candidate_tools)))
    selected = tuple(sorted(set(selected_tools)))
    actual = tuple(sorted(set(actual_exposed_tools)))

    if not set(selected).issubset(set(candidates)):
        raise ToolExposureWidenedError("SELECTED_TOOLS_EXCEED_CANDIDATE_TOOLS")

    if not set(actual).issubset(set(selected)):
        raise ToolExposureWidenedError("ACTUAL_EXPOSED_TOOLS_EXCEED_SELECTED_TOOLS")

    material = {
        "schema": TOOL_EXPOSURE_RECEIPT_SCHEMA,
        "operation_id": op_id,
        "attempt_id": att_id,
        "provider": prov,
        "backend_id": backend,
        "planner_decision_hash": dec_hash,
        "projection_hash": proj_hash,
        "enforcement_mode": enforcement_mode,
        "candidate_tools": list(candidates),
        "selected_tools": list(selected),
        "actual_exposed_tools": list(actual),
        "actual_exposed_tool_count": len(actual),
        "authority_kind": "DERIVED_EXPOSURE_EVIDENCE_ONLY",
    }
    exposure_hash = _sha256(material)
    return {**material, "exposure_hash": exposure_hash}


def validate_tool_exposure_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_operation_id: str | None = None,
    expected_attempt_id: str | None = None,
    expected_planner_decision_hash: str | None = None,
    expected_projection_hash: str | None = None,
    expected_provider: str | None = None,
    expected_backend_id: str | None = None,
) -> dict[str, Any]:
    """Validate a tool exposure receipt fail-closed.

    Rejects missing fields, hash mismatches, identity drift, and tool widening.
    """
    if not isinstance(receipt, Mapping):
        raise ToolExposureError("TOOL_EXPOSURE_RECEIPT_NOT_MAPPING")

    if set(receipt) != _EXPECTED_FIELDS:
        raise ToolExposureError("TOOL_EXPOSURE_RECEIPT_FIELDS_INVALID")

    if receipt.get("schema") != TOOL_EXPOSURE_RECEIPT_SCHEMA:
        raise ToolExposureError("TOOL_EXPOSURE_RECEIPT_SCHEMA_INVALID")

    if receipt.get("authority_kind") != "DERIVED_EXPOSURE_EVIDENCE_ONLY":
        raise ToolExposureError("TOOL_EXPOSURE_AUTHORITY_KIND_INVALID")

    op_id = _require_text(receipt.get("operation_id"), "operation_id")
    att_id = _require_text(receipt.get("attempt_id"), "attempt_id")
    prov = _require_text(receipt.get("provider"), "provider")
    backend = _require_text(receipt.get("backend_id"), "backend_id")
    dec_hash = _require_hex64(receipt.get("planner_decision_hash"), "planner_decision_hash")
    proj_hash = _require_hex64(receipt.get("projection_hash"), "projection_hash")

    if expected_operation_id is not None and op_id != expected_operation_id:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_OPERATION_MISMATCH")
    if expected_attempt_id is not None and att_id != expected_attempt_id:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_ATTEMPT_MISMATCH")
    if expected_planner_decision_hash is not None and dec_hash != expected_planner_decision_hash:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_PLANNER_DECISION_MISMATCH")
    if expected_projection_hash is not None and proj_hash != expected_projection_hash:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_PROJECTION_MISMATCH")
    if expected_provider is not None and prov != expected_provider:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_PROVIDER_MISMATCH")
    if expected_backend_id is not None and backend != expected_backend_id:
        raise ToolExposureIdentityError("TOOL_EXPOSURE_BACKEND_MISMATCH")

    mode = receipt.get("enforcement_mode")
    if mode not in ENFORCEMENT_MODES:
        raise ToolExposureError(f"enforcement_mode_invalid:{mode}")

    candidates = receipt.get("candidate_tools")
    selected = receipt.get("selected_tools")
    actual = receipt.get("actual_exposed_tools")

    if (
        not isinstance(candidates, list)
        or not isinstance(selected, list)
        or not isinstance(actual, list)
    ):
        raise ToolExposureError("TOOL_EXPOSURE_LISTS_INVALID")

    if not set(selected).issubset(set(candidates)):
        raise ToolExposureWidenedError("SELECTED_TOOLS_EXCEED_CANDIDATE_TOOLS")

    if not set(actual).issubset(set(selected)):
        raise ToolExposureWidenedError("ACTUAL_EXPOSED_TOOLS_EXCEED_SELECTED_TOOLS")

    if len(actual) != receipt.get("actual_exposed_tool_count"):
        raise ToolExposureError("ACTUAL_EXPOSED_TOOL_COUNT_MISMATCH")

    material = dict(receipt)
    claimed_hash = material.pop("exposure_hash")
    if not isinstance(claimed_hash, str) or _SHA256_RE.fullmatch(claimed_hash) is None:
        raise ToolExposureError("TOOL_EXPOSURE_HASH_MALFORMED")

    if _sha256(material) != claimed_hash:
        raise ToolExposureError("TOOL_EXPOSURE_HASH_MISMATCH")

    return dict(receipt)
