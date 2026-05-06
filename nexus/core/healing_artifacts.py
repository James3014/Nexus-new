from __future__ import annotations

import json
import hmac
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nexus.core.belief_contracts import HealingArtifact


SIGNATURE_ALGORITHM = "hmac-sha256"


def _canonical_artifact_payload(artifact: HealingArtifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload.pop("signature", None)
    payload.pop("signature_key_id", None)
    return payload


def _canonical_artifact_bytes(artifact: HealingArtifact) -> bytes:
    return json.dumps(
        _canonical_artifact_payload(artifact),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_healing_artifact(artifact: HealingArtifact, *, key: str | bytes, key_id: str = "local") -> HealingArtifact:
    """Return a signed copy of a healing artifact without mutating the original."""
    key_bytes = key.encode("utf-8") if isinstance(key, str) else bytes(key)
    signature = hmac.new(key_bytes, _canonical_artifact_bytes(artifact), hashlib.sha256).hexdigest()
    return HealingArtifact(
        **{
            **_canonical_artifact_payload(artifact),
            "signature": f"{SIGNATURE_ALGORITHM}:{signature}",
            "signature_key_id": key_id,
        }
    )


def verify_healing_artifact_signature(artifact: HealingArtifact, *, key: str | bytes) -> bool:
    """Verify artifact body integrity using the embedded HMAC signature."""
    if not artifact.signature.startswith(f"{SIGNATURE_ALGORITHM}:"):
        return False
    expected = sign_healing_artifact(artifact, key=key, key_id=artifact.signature_key_id).signature
    return hmac.compare_digest(expected, artifact.signature)


def write_healing_artifact(project_root: str | Path, artifact: HealingArtifact) -> Path:
    """Persist a portable healing artifact for later route/report citation."""
    root = Path(project_root)
    out_dir = root / ".nexus" / "artifacts" / "healing"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in artifact.artifact_id).strip("-") or "healing-artifact"
    out_path = out_dir / f"{safe_id}.json"
    out_path.write_text(json.dumps(asdict(artifact), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def read_healing_artifact(path: str | Path) -> HealingArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return HealingArtifact(**payload)


def artifact_to_packet(artifact: HealingArtifact) -> dict:
    """Serialize healing advice for safe swarm transport without executing it."""
    return {
        "type": "healing_artifact",
        "schema_version": "nexus_healing_artifact.v1",
        "payload": asdict(artifact),
    }


def artifact_from_packet(packet: dict) -> HealingArtifact:
    if packet.get("type") != "healing_artifact":
        raise ValueError("not a healing artifact packet")
    if packet.get("schema_version") != "nexus_healing_artifact.v1":
        raise ValueError("unsupported healing artifact schema")
    payload = packet.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("healing artifact packet payload must be an object")
    return HealingArtifact(**payload)


def healing_artifact_report_entry(path: str | Path) -> dict:
    """Read a persisted artifact into a report-safe citation row."""
    artifact = read_healing_artifact(path)
    return {
        "artifact_id": artifact.artifact_id,
        "task_id": artifact.task_id,
        "artifact_type": artifact.artifact_type,
        "evidence_id": artifact.evidence_id,
        "summary": artifact.summary,
        "path": str(path),
    }
