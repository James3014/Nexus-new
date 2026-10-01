from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

TOOL_EXPOSURE_RECEIPT_SCHEMA = "nexus.tool_exposure_receipt.v1"
STABLE_TOOL_IDENTITY_SCHEMA = "nexus.stable_tool_identity.v1"
RUNTIME_TOOL_GENERATION_SCHEMA = "nexus.runtime_tool_generation.v1"

ENFORCEMENT_MODES = frozenset({
    "ENFORCED_NATIVE_PROVIDER",
    "ENFORCED_MANAGED_BRIDGE",
    "REQUEST_ONLY_NOT_ENFORCED",
    "NOT_OBSERVED",
    "NO_EXTERNAL_TOOL_SURFACE",
    "UNKNOWN",
})

PHYSICALLY_ENFORCED_MODES = frozenset({
    "ENFORCED_NATIVE_PROVIDER",
    "ENFORCED_MANAGED_BRIDGE",
})

_CORE_FIELDS = frozenset({
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
})

_OPTIONAL_FIELDS = frozenset({
    "remote_tool_identities",
    "runtime_tool_generations",
})

_ALL_FIELDS = _CORE_FIELDS | _OPTIONAL_FIELDS
_EXPECTED_FIELDS = _ALL_FIELDS

_STABLE_TOOL_IDENTITY_FIELDS = frozenset({
    "schema",
    "server_origin",
    "tool_name",
    "input_schema_hash",
    "description_hash",
    "stable_tool_id",
})

_RUNTIME_TOOL_GENERATION_FIELDS = frozenset({
    "schema",
    "server_origin",
    "server_instance_id",
    "source_commit",
    "build_id",
    "capability_manifest_sha256",
    "catalog_generation",
    "generation_hash",
    "observed_at",
})

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


def compute_tool_input_schema_hash(schema: Mapping[str, Any] | str | None) -> str:
    """Compute sha256 hex digest for an input schema."""
    if schema is None:
        return _sha256({})
    if isinstance(schema, str):
        schema_str = schema.strip()
        if len(schema_str) == 64 and _SHA256_RE.fullmatch(schema_str):
            return schema_str
        try:
            parsed = json.loads(schema_str)
            return _sha256(parsed)
        except Exception:
            return _sha256({"raw": schema_str})
    return _sha256(schema)


def compute_tool_description_hash(description: str | None) -> str:
    """Compute sha256 hex digest for a tool description."""
    desc = (description or "").strip()
    if len(desc) == 64 and _SHA256_RE.fullmatch(desc):
        return desc
    return hashlib.sha256(desc.encode("utf-8")).hexdigest()


def compute_stable_tool_id(
    *,
    server_origin: str,
    tool_name: str,
    input_schema_hash: str,
    description_hash: str,
) -> str:
    """Compute durable stable tool authority identity hash."""
    payload = {
        "description_hash": _require_hex64(description_hash, "description_hash"),
        "input_schema_hash": _require_hex64(input_schema_hash, "input_schema_hash"),
        "server_origin": _require_text(server_origin, "server_origin"),
        "tool_name": _require_text(tool_name, "tool_name"),
    }
    return _sha256(payload)


def build_stable_tool_identity(
    *,
    server_origin: str,
    tool_name: str,
    input_schema: Mapping[str, Any] | str | None = None,
    input_schema_hash: str | None = None,
    description: str | None = None,
    description_hash: str | None = None,
) -> dict[str, Any]:
    """Construct a Stable Tool Authority Identity.

    Durable approved capability identity: (server/origin + tool + input schema hash + description hash).
    Server instance ID is NOT baked into this stable identity.
    """
    origin = _require_text(server_origin, "server_origin")
    name = _require_text(tool_name, "tool_name")

    if input_schema_hash is not None:
        s_hash = _require_hex64(input_schema_hash, "input_schema_hash")
    else:
        s_hash = compute_tool_input_schema_hash(input_schema)

    if description_hash is not None:
        d_hash = _require_hex64(description_hash, "description_hash")
    else:
        d_hash = compute_tool_description_hash(description)

    stable_id = compute_stable_tool_id(
        server_origin=origin,
        tool_name=name,
        input_schema_hash=s_hash,
        description_hash=d_hash,
    )
    return {
        "schema": STABLE_TOOL_IDENTITY_SCHEMA,
        "server_origin": origin,
        "tool_name": name,
        "input_schema_hash": s_hash,
        "description_hash": d_hash,
        "stable_tool_id": stable_id,
    }


def validate_stable_tool_identity(
    identity: Mapping[str, Any],
    *,
    expected_server_origin: str | None = None,
    expected_tool_name: str | None = None,
    expected_input_schema_hash: str | None = None,
    expected_description_hash: str | None = None,
    expected_stable_tool_id: str | None = None,
) -> dict[str, Any]:
    """Validate a Stable Tool Authority Identity fail-closed."""
    if not isinstance(identity, Mapping):
        raise ToolExposureError("STABLE_TOOL_IDENTITY_NOT_MAPPING")

    if set(identity) != _STABLE_TOOL_IDENTITY_FIELDS:
        raise ToolExposureError("STABLE_TOOL_IDENTITY_FIELDS_INVALID")

    if identity.get("schema") != STABLE_TOOL_IDENTITY_SCHEMA:
        raise ToolExposureError("STABLE_TOOL_IDENTITY_SCHEMA_INVALID")

    origin = _require_text(identity.get("server_origin"), "server_origin")
    name = _require_text(identity.get("tool_name"), "tool_name")
    s_hash = _require_hex64(identity.get("input_schema_hash"), "input_schema_hash")
    d_hash = _require_hex64(identity.get("description_hash"), "description_hash")
    claimed_id = _require_hex64(identity.get("stable_tool_id"), "stable_tool_id")

    computed_id = compute_stable_tool_id(
        server_origin=origin,
        tool_name=name,
        input_schema_hash=s_hash,
        description_hash=d_hash,
    )
    if claimed_id != computed_id:
        raise ToolExposureError("STABLE_TOOL_ID_MISMATCH")

    if expected_server_origin is not None and origin != expected_server_origin:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_SERVER_ORIGIN_MISMATCH: expected {expected_server_origin}, got {origin}"
        )
    if expected_tool_name is not None and name != expected_tool_name:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_NAME_MISMATCH: expected {expected_tool_name}, got {name}"
        )
    if expected_input_schema_hash is not None and s_hash != expected_input_schema_hash:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_INPUT_SCHEMA_MISMATCH: expected {expected_input_schema_hash}, got {s_hash}"
        )
    if expected_description_hash is not None and d_hash != expected_description_hash:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_DESCRIPTION_MISMATCH: expected {expected_description_hash}, got {d_hash}"
        )
    if expected_stable_tool_id is not None and claimed_id != expected_stable_tool_id:
        raise ToolExposureIdentityError(
            f"REMOTE_STABLE_TOOL_ID_MISMATCH: expected {expected_stable_tool_id}, got {claimed_id}"
        )

    return dict(identity)


def compute_runtime_generation_hash(
    *,
    server_origin: str,
    server_instance_id: str,
    source_commit: str,
    build_id: str,
    capability_manifest_sha256: str,
    catalog_generation: int | str,
) -> str:
    """Compute ephemeral runtime tool generation evidence hash."""
    payload = {
        "build_id": _require_text(build_id, "build_id"),
        "capability_manifest_sha256": _require_hex64(
            capability_manifest_sha256, "capability_manifest_sha256"
        ),
        "catalog_generation": catalog_generation,
        "server_instance_id": _require_text(server_instance_id, "server_instance_id"),
        "server_origin": _require_text(server_origin, "server_origin"),
        "source_commit": _require_text(source_commit, "source_commit"),
    }
    return _sha256(payload)


def build_runtime_tool_generation(
    *,
    server_origin: str,
    server_instance_id: str,
    source_commit: str,
    build_id: str,
    capability_manifest_sha256: str,
    catalog_generation: int | str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Construct physical runtime-generation evidence for a remote tool server."""
    origin = _require_text(server_origin, "server_origin")
    instance_id = _require_text(server_instance_id, "server_instance_id")
    source = _require_text(source_commit, "source_commit")
    build = _require_text(build_id, "build_id")
    manifest = _require_hex64(capability_manifest_sha256, "capability_manifest_sha256")
    if not isinstance(catalog_generation, (int, str)) or str(catalog_generation).strip() == "":
        raise ToolExposureError("catalog_generation_invalid")
    gen = (
        catalog_generation
        if isinstance(catalog_generation, int)
        else str(catalog_generation).strip()
    )
    obs_at = str(observed_at or "1970-01-01T00:00:00Z").strip()
    gen_hash = compute_runtime_generation_hash(
        server_origin=origin,
        server_instance_id=instance_id,
        source_commit=source,
        build_id=build,
        capability_manifest_sha256=manifest,
        catalog_generation=gen,
    )
    return {
        "schema": RUNTIME_TOOL_GENERATION_SCHEMA,
        "server_origin": origin,
        "server_instance_id": instance_id,
        "source_commit": source,
        "build_id": build,
        "capability_manifest_sha256": manifest,
        "catalog_generation": gen,
        "generation_hash": gen_hash,
        "observed_at": obs_at,
    }


def validate_runtime_tool_generation(
    generation: Mapping[str, Any],
    *,
    expected_server_origin: str | None = None,
    expected_server_instance_id: str | None = None,
    expected_source_commit: str | None = None,
    expected_build_id: str | None = None,
    expected_capability_manifest_sha256: str | None = None,
    expected_catalog_generation: int | str | None = None,
) -> dict[str, Any]:
    """Validate ephemeral runtime tool generation evidence fail-closed."""
    if not isinstance(generation, Mapping):
        raise ToolExposureError("RUNTIME_TOOL_GENERATION_NOT_MAPPING")

    if set(generation) != _RUNTIME_TOOL_GENERATION_FIELDS:
        raise ToolExposureError("RUNTIME_TOOL_GENERATION_FIELDS_INVALID")

    if generation.get("schema") != RUNTIME_TOOL_GENERATION_SCHEMA:
        raise ToolExposureError("RUNTIME_TOOL_GENERATION_SCHEMA_INVALID")

    origin = _require_text(generation.get("server_origin"), "server_origin")
    instance_id = _require_text(generation.get("server_instance_id"), "server_instance_id")
    source = _require_text(generation.get("source_commit"), "source_commit")
    build = _require_text(generation.get("build_id"), "build_id")
    manifest = _require_hex64(
        generation.get("capability_manifest_sha256"), "capability_manifest_sha256"
    )
    cat_gen = generation.get("catalog_generation")
    if not isinstance(cat_gen, (int, str)) or str(cat_gen).strip() == "":
        raise ToolExposureError("catalog_generation_invalid")
    gen = cat_gen if isinstance(cat_gen, int) else str(cat_gen).strip()
    claimed_hash = _require_hex64(generation.get("generation_hash"), "generation_hash")

    computed_hash = compute_runtime_generation_hash(
        server_origin=origin,
        server_instance_id=instance_id,
        source_commit=source,
        build_id=build,
        capability_manifest_sha256=manifest,
        catalog_generation=gen,
    )
    if claimed_hash != computed_hash:
        raise ToolExposureError("RUNTIME_GENERATION_HASH_MISMATCH")

    if expected_server_origin is not None and origin != expected_server_origin:
        raise ToolExposureIdentityError(
            f"RUNTIME_GENERATION_SERVER_ORIGIN_MISMATCH: expected {expected_server_origin}, got {origin}"
        )
    if expected_server_instance_id is not None and instance_id != expected_server_instance_id:
        raise ToolExposureIdentityError(
            f"RUNTIME_GENERATION_SERVER_INSTANCE_MISMATCH: expected {expected_server_instance_id}, got {instance_id}"
        )
    if expected_source_commit is not None and source != expected_source_commit:
        raise ToolExposureIdentityError(
            f"RUNTIME_GENERATION_SOURCE_COMMIT_MISMATCH: expected {expected_source_commit}, got {source}"
        )
    if expected_build_id is not None and build != expected_build_id:
        raise ToolExposureIdentityError(
            f"RUNTIME_GENERATION_BUILD_ID_MISMATCH: expected {expected_build_id}, got {build}"
        )
    if (
        expected_capability_manifest_sha256 is not None
        and manifest != expected_capability_manifest_sha256
    ):
        raise ToolExposureIdentityError(
            "RUNTIME_GENERATION_CAPABILITY_MANIFEST_MISMATCH: "
            f"expected {expected_capability_manifest_sha256}, got {manifest}"
        )
    if expected_catalog_generation is not None and gen != expected_catalog_generation:
        raise ToolExposureIdentityError(
            f"RUNTIME_GENERATION_CATALOG_GENERATION_MISMATCH: expected {expected_catalog_generation}, got {gen}"
        )

    return dict(generation)


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
    remote_tool_identities: Sequence[Mapping[str, Any]] | None = None,
    runtime_tool_generations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construct a canonical derived physical-exposure evidence record.

    Invariants:
    1. selected_tools <= candidate_tools
    2. actual_exposed_tools <= selected_tools
    3. enforcement_mode in ENFORCEMENT_MODES
    4. remote_tool_identities and runtime_tool_generations are validated and deterministically ordered
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

    validated_remote = [
        validate_stable_tool_identity(ident) for ident in (remote_tool_identities or ())
    ]
    validated_remote.sort(key=lambda x: (x["server_origin"], x["tool_name"], x["stable_tool_id"]))

    validated_gens = [
        validate_runtime_tool_generation(gen) for gen in (runtime_tool_generations or ())
    ]
    validated_gens.sort(
        key=lambda x: (
            x["server_origin"],
            str(x["catalog_generation"]),
            x["server_instance_id"],
        )
    )

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
        "remote_tool_identities": validated_remote,
        "runtime_tool_generations": validated_gens,
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
    expected_remote_tool_identities: Sequence[Mapping[str, Any]] | None = None,
    expected_runtime_tool_generations: Sequence[Mapping[str, Any]] | None = None,
    require_remote_tool_identity: bool = False,
) -> dict[str, Any]:
    """Validate a tool exposure receipt fail-closed.

    Rejects missing fields, hash mismatches, identity drift, tool widening,
    and unapproved remote tool identity / runtime generation drift.
    """
    if not isinstance(receipt, Mapping):
        raise ToolExposureError("TOOL_EXPOSURE_RECEIPT_NOT_MAPPING")

    receipt_keys = set(receipt)
    if not (receipt_keys == _CORE_FIELDS or receipt_keys == _ALL_FIELDS):
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

    # Validate remote tool identities
    raw_remotes = receipt.get("remote_tool_identities") or []
    if not isinstance(raw_remotes, (list, tuple)):
        raise ToolExposureError("REMOTE_TOOL_IDENTITIES_INVALID")
    validated_remotes = [validate_stable_tool_identity(r) for r in raw_remotes]

    if require_remote_tool_identity and not validated_remotes:
        raise ToolExposureIdentityError("MISSING_REMOTE_TOOL_IDENTITY_EVIDENCE")

    if expected_remote_tool_identities is not None:
        if not validated_remotes:
            raise ToolExposureIdentityError("MISSING_REMOTE_TOOL_IDENTITY_EVIDENCE")
        validated_expected_remotes = [
            validate_stable_tool_identity(exp) for exp in expected_remote_tool_identities
        ]
        for exp in validated_expected_remotes:
            exp_origin = exp["server_origin"]
            exp_name = exp["tool_name"]
            exp_schema_hash = exp["input_schema_hash"]
            exp_desc_hash = exp["description_hash"]
            exp_stable_id = exp["stable_tool_id"]

            match = next(
                (
                    r
                    for r in validated_remotes
                    if r.get("server_origin") == exp_origin and r.get("tool_name") == exp_name
                ),
                None,
            )
            if match is None:
                raise ToolExposureIdentityError(
                    f"REMOTE_TOOL_IDENTITY_NOT_FOUND: {exp_origin}/{exp_name}"
                )

            if match.get("input_schema_hash") != exp_schema_hash:
                raise ToolExposureIdentityError(
                    f"REMOTE_TOOL_INPUT_SCHEMA_MISMATCH: expected {exp_schema_hash}, got {match.get('input_schema_hash')}"
                )
            if match.get("description_hash") != exp_desc_hash:
                raise ToolExposureIdentityError(
                    f"REMOTE_TOOL_DESCRIPTION_MISMATCH: expected {exp_desc_hash}, got {match.get('description_hash')}"
                )
            if match.get("stable_tool_id") != exp_stable_id:
                raise ToolExposureIdentityError(
                    f"REMOTE_STABLE_TOOL_ID_MISMATCH: expected {exp_stable_id}, got {match.get('stable_tool_id')}"
                )

    # Validate runtime tool generations
    raw_gens = receipt.get("runtime_tool_generations") or []
    if not isinstance(raw_gens, (list, tuple)):
        raise ToolExposureError("RUNTIME_TOOL_GENERATIONS_INVALID")
    validated_gens = [validate_runtime_tool_generation(g) for g in raw_gens]

    if expected_runtime_tool_generations is not None:
        validated_expected_gens = [
            validate_runtime_tool_generation(g) for g in expected_runtime_tool_generations
        ]
        for exp_g in validated_expected_gens:
            exp_orig = exp_g["server_origin"]
            exp_inst = exp_g["server_instance_id"]
            exp_source = exp_g["source_commit"]
            exp_build = exp_g["build_id"]
            exp_manifest = exp_g["capability_manifest_sha256"]
            exp_cat = exp_g["catalog_generation"]

            match_g = next(
                (g for g in validated_gens if g.get("server_origin") == exp_orig),
                None,
            )
            if match_g is None:
                raise ToolExposureIdentityError(f"RUNTIME_GENERATION_NOT_FOUND: {exp_orig}")

            if match_g.get("server_instance_id") != exp_inst:
                raise ToolExposureIdentityError(
                    f"RUNTIME_GENERATION_SERVER_INSTANCE_MISMATCH: expected {exp_inst}, got {match_g.get('server_instance_id')}"
                )
            if match_g.get("source_commit") != exp_source:
                raise ToolExposureIdentityError(
                    f"RUNTIME_GENERATION_SOURCE_COMMIT_MISMATCH: expected {exp_source}, got {match_g.get('source_commit')}"
                )
            if match_g.get("build_id") != exp_build:
                raise ToolExposureIdentityError(
                    f"RUNTIME_GENERATION_BUILD_ID_MISMATCH: expected {exp_build}, got {match_g.get('build_id')}"
                )
            if match_g.get("capability_manifest_sha256") != exp_manifest:
                raise ToolExposureIdentityError(
                    "RUNTIME_GENERATION_CAPABILITY_MANIFEST_MISMATCH: "
                    f"expected {exp_manifest}, got {match_g.get('capability_manifest_sha256')}"
                )
            if match_g.get("catalog_generation") != exp_cat:
                raise ToolExposureIdentityError(
                    f"RUNTIME_GENERATION_CATALOG_GENERATION_MISMATCH: expected {exp_cat}, got {match_g.get('catalog_generation')}"
                )

    return dict(receipt)
