"""
Abort Receipt Guarantee: If run starts, receipt must exist.
Even workspace provisioning failures produce an abort receipt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


WORKSPACE_FAILURE_SUBCLASSES = [
    "REPO_NOT_MOUNTED",
    "WORKSPACE_NOT_WRITABLE",
    "TARGET_PATH_UNRESOLVED",
    "MANIFEST_MISSING_TARGET",
    "WRONG_REPRO_PATH",
    "STALE_MODEL_PATH",
]


@dataclass
class AbortReceipt:
    """Abort receipt produced when a run cannot complete."""
    schema: str = "nexus.evidence.abort_receipt.v1"
    task_id: str = ""
    instance_id: str = ""
    receipt_present: bool = True
    solved: bool = False
    claim_eligible: bool = False
    simulated: bool = False
    failure_class: str = "workspace_provisioning"
    failure_reason: str = ""
    failure_subclass: str = ""
    workspace_path: str = ""
    repo_root: str = ""
    target_path: str = ""
    path_subclass: str = ""
    model_calls: int = 0
    stop_layer: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def write_abort_receipt(
    *,
    output_dir: Path,
    task_id: str,
    instance_id: str,
    failure_class: str = "workspace_provisioning",
    failure_reason: str = "",
    failure_subclass: str = "",
    workspace_path: str = "",
    repo_root: str = "",
    target_path: str = "",
    path_subclass: str = "",
    model_calls: int = 0,
    stop_layer: str = "",
    started_at: Optional[str] = None,
) -> Path:
    """Write an abort receipt and return the path."""
    now = datetime.now(timezone.utc).isoformat()
    receipt = AbortReceipt(
        task_id=task_id,
        instance_id=instance_id,
        failure_class=failure_class,
        failure_reason=failure_reason,
        failure_subclass=failure_subclass,
        workspace_path=workspace_path,
        repo_root=repo_root,
        target_path=target_path,
        path_subclass=path_subclass,
        model_calls=model_calls,
        stop_layer=stop_layer,
        started_at=started_at or now,
        finished_at=now,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / f"abort_receipt_{task_id}.json"
    receipt_path.write_text(receipt.to_json(), encoding="utf-8")
    return receipt_path


def load_abort_receipt(path: Path) -> dict:
    """Load an abort receipt from disk."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_failure_subclass(subclass: str) -> bool:
    """Check if a failure subclass is in the allowed list."""
    return subclass in WORKSPACE_FAILURE_SUBCLASSES
