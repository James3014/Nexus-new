"""Durable artifact storage for Local Model Nexus Armor.

Production decision receipts, ledgers, and operator logs must land under a
workspace or Nexus artifact root — never the OS ephemeral temp root by default.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

ENV_ARMOR_ARTIFACT_ROOT = "NEXUS_ARMOR_ARTIFACT_ROOT"
ENV_ARMOR_WORKSPACE_ROOT = "NEXUS_ARMOR_WORKSPACE_ROOT"
ENV_ARMOR_ALLOW_EPHEMERAL = "NEXUS_ARMOR_ALLOW_EPHEMERAL"

DEFAULT_REPORTS_REL = Path(".nexus/reports/local_heal")
DEFAULT_ARTIFACTS_REL = Path(".nexus/artifacts/local_armor")
DEFAULT_WORKSPACES_REL = Path(".nexus/artifacts/local_armor/workspaces")
DEFAULT_REPLAY_REL = Path(".nexus/artifacts/local_armor/replay")
DEFAULT_OPERATOR_LOG_REL = Path(".nexus/artifacts/local_armor/operator")

_EPHEMERAL_MARKERS = (
    "/var/folders/",
    "/private/var/folders/",
    "/tmp/",
    "/private/tmp/",
    "\\AppData\\Local\\Temp\\",
    "\\Temp\\",
)


def nexus_workspace_root(env: Mapping[str, str] | None = None) -> Path:
    """Resolve the Nexus workspace root used for durable Armor artifacts."""
    env_map = env if env is not None else os.environ
    explicit = str(env_map.get(ENV_ARMOR_WORKSPACE_ROOT, "") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _allow_ephemeral(env: Mapping[str, str]) -> bool:
    return str(env.get(ENV_ARMOR_ALLOW_EPHEMERAL, "") or "").strip() in (
        "1",
        "true",
        "TRUE",
        "yes",
    )


def resolve_armor_artifact_root(
    *,
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return the durable Armor artifact root (never OS temp by default)."""
    env_map = env if env is not None else os.environ
    explicit = str(env_map.get(ENV_ARMOR_ARTIFACT_ROOT, "") or "").strip()
    if explicit:
        root = Path(explicit).expanduser().resolve()
    else:
        base = (
            Path(workspace_root).expanduser().resolve()
            if workspace_root
            else nexus_workspace_root(env_map)
        )
        root = (base / DEFAULT_ARTIFACTS_REL).resolve()
    if is_ephemeral_path(root) and not _allow_ephemeral(env_map):
        raise ValueError(
            f"Armor artifact root must not be ephemeral OS temp: {root}. "
            f"Set {ENV_ARMOR_ARTIFACT_ROOT} to a durable workspace path."
        )
    return root


def default_local_heal_reports_root(
    *,
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Default durable root for repair receipts (legacy-compatible path)."""
    env_map = env if env is not None else os.environ
    artifact = str(env_map.get(ENV_ARMOR_ARTIFACT_ROOT, "") or "").strip()
    if artifact:
        return Path(artifact).expanduser().resolve() / "reports" / "local_heal"
    base = (
        Path(workspace_root).expanduser().resolve()
        if workspace_root
        else nexus_workspace_root(env_map)
    )
    return (base / DEFAULT_REPORTS_REL).resolve()


def resolve_isolated_work_root(
    work_dir: str | Path | None = None,
    *,
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve parent dir for isolated apply workspaces."""
    if work_dir:
        root = Path(work_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    env_map = env if env is not None else os.environ
    base = resolve_armor_artifact_root(workspace_root=workspace_root, env=env_map)
    root = (base / "workspaces").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_isolated_workspace(
    *,
    work_dir: str | Path | None = None,
    prefix: str = "armor-apply-",
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Create an isolated workspace under a durable parent."""
    parent = resolve_isolated_work_root(
        work_dir,
        workspace_root=workspace_root,
        env=env,
    )
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))


def resolve_repro_script_dir(
    *,
    work_dir: str | Path | None = None,
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Directory for ephemeral-but-replayable repro scripts (not /tmp)."""
    if work_dir:
        root = Path(work_dir).expanduser().resolve()
    else:
        root = (
            resolve_armor_artifact_root(workspace_root=workspace_root, env=env)
            / "repro"
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_ephemeral_path(path: Path | str | None) -> bool:
    """True if path resolves under a known OS ephemeral temp root."""
    if path is None:
        return False
    try:
        text = str(Path(path).expanduser().resolve()).replace("\\", "/")
    except OSError:
        text = str(path).replace("\\", "/")
    lowered = text.lower()
    system_tmp = str(Path(tempfile.gettempdir()).resolve()).replace("\\", "/").lower()
    if system_tmp and (
        lowered == system_tmp or lowered.startswith(system_tmp.rstrip("/") + "/")
    ):
        return True
    return any(marker.lower() in lowered for marker in _EPHEMERAL_MARKERS)


def assert_durable_path(path: Path | str, *, label: str = "path") -> Path:
    """Fail closed if a production artifact path would be ephemeral."""
    resolved = Path(path).expanduser().resolve()
    if is_ephemeral_path(resolved):
        raise ValueError(f"{label} must be durable (not OS temp): {resolved}")
    return resolved


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value).strip("_") or "unknown"


REPLAY_REQUIRED_FIELDS = (
    "schema",
    "task_id",
    "instance_id",
    "gate_passed",
    "solve_eligible",
    "failure_reason",
    "evidence_refs",
    "final_receipt_path",
)


def write_json_artifact(
    path: Path | str,
    payload: Mapping[str, Any],
    *,
    require_durable: bool = True,
) -> Path:
    """Write a JSON artifact, optionally refusing ephemeral destinations."""
    target = Path(path)
    if require_durable:
        assert_durable_path(
            target.parent if target.suffix else target,
            label="artifact parent",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target.resolve()


def load_repair_receipt(path: Path | str) -> dict[str, Any]:
    """Load a repair receipt JSON from durable storage."""
    receipt_path = Path(path)
    if not receipt_path.is_file():
        raise FileNotFoundError(f"receipt not found: {receipt_path}")
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("receipt payload must be a JSON object")
    return data


def reconstruct_decision_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the minimal decision surface needed for operator replay."""
    telemetries = (
        receipt.get("telemetries")
        if isinstance(receipt.get("telemetries"), dict)
        else {}
    )
    model_decisions = (
        telemetries.get("model_decisions") if isinstance(telemetries, dict) else None
    )
    if not isinstance(model_decisions, list):
        model_decisions = (
            receipt.get("model_decisions")
            if isinstance(receipt.get("model_decisions"), list)
            else []
        )
    latency_ledger = receipt.get("latency_ledger")
    if latency_ledger is None and isinstance(telemetries, dict):
        latency_ledger = telemetries.get("latency_ledger")

    decision = {
        "schema": receipt.get("schema", ""),
        "schema_version": receipt.get("schema_version", ""),
        "task_id": receipt.get("task_id") or receipt.get("instance_id") or "",
        "instance_id": receipt.get("instance_id") or receipt.get("task_id") or "",
        "gate_passed": bool(receipt.get("gate_passed", False)),
        "solve_eligible": bool(receipt.get("solve_eligible", False)),
        "failure_reason": str(receipt.get("failure_reason", "") or ""),
        "verifier_result": _derive_verifier_result(receipt),
        "routing": {
            "p3_shadow_route_mode": receipt.get("p3_shadow_route_mode", ""),
            "p3_shadow_authority": receipt.get("p3_shadow_authority", ""),
            "execution_topology": telemetries.get("execution_topology")
            if isinstance(telemetries, dict)
            else receipt.get("execution_topology", ""),
            "local_armor_execution_profile": telemetries.get(
                "local_armor_execution_profile"
            )
            or receipt.get("local_armor_execution_profile")
            or "",
        },
        "evidence_refs": list(receipt.get("evidence_refs") or []),
        "model_decisions": list(model_decisions or []),
        "latency_ledger": latency_ledger,
        "final_receipt_path": str(receipt.get("final_receipt_path", "") or ""),
        "claim_boundary": {
            "public_claim_allowed": bool(receipt.get("public_claim_allowed", False)),
            "production_ready": bool(receipt.get("production_ready", False)),
            "claim_eligible": bool(receipt.get("claim_eligible", False)),
            "internal_only": bool(receipt.get("internal_only", True)),
        },
        "replayable": True,
    }
    missing = [field for field in ("schema", "task_id") if not decision.get(field)]
    decision["replay_complete"] = len(missing) == 0 and bool(
        decision["evidence_refs"] is not None
    )
    decision["replay_missing_fields"] = missing
    return decision


def load_decision_for_replay(receipt_path: Path | str) -> dict[str, Any]:
    """Load receipt from disk and reconstruct a replayable decision."""
    receipt = load_repair_receipt(receipt_path)
    decision = reconstruct_decision_from_receipt(receipt)
    decision["source_receipt_path"] = str(Path(receipt_path).resolve())
    if is_ephemeral_path(receipt_path):
        decision["source_is_ephemeral"] = True
        decision["replayable"] = False
        decision.setdefault("replay_missing_fields", []).append("source_path_ephemeral")
    else:
        decision["source_is_ephemeral"] = False
    return decision


def _derive_verifier_result(receipt: Mapping[str, Any]) -> str:
    if receipt.get("gate_passed") is True or receipt.get("solve_eligible") is True:
        return "pass"
    if receipt.get("hidden_verifier_passed") is True and receipt.get(
        "solve_eligible"
    ) is False:
        return "fail"
    reason = str(receipt.get("failure_reason", "") or "")
    if "VERIFICATION" in reason or "ASSERT" in reason.upper():
        return "fail"
    if reason:
        return "blocked"
    return "not_run"


def operator_log_path(
    name: str = "operator_last.json",
    *,
    workspace_root: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    root = resolve_armor_artifact_root(workspace_root=workspace_root, env=env)
    return (root / "operator" / name).resolve()
