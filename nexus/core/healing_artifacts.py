from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from nexus.core.belief_contracts import HealingArtifact
from nexus.core.evolution_protocols import build_quiet_moment_event


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


def quiet_moment_healing_packet(
    *,
    reason: str,
    affected_nodes: list[str] | tuple[str, ...],
    resume_after_seconds: int,
    evidence_id: str,
) -> dict:
    """Attach a non-mutating swarm pause event to healing evidence."""
    event = build_quiet_moment_event(
        reason=reason,
        affected_nodes=affected_nodes,
        resume_after_seconds=resume_after_seconds,
    )
    return {
        "type": "quiet_moment_healing_packet",
        "schema_version": "nexus_quiet_moment_healing_packet.v1",
        "evidence_id": evidence_id,
        "event": event,
        "production_writes_allowed": False,
    }


def quiet_moment_report_entry(packet: dict) -> dict:
    if packet.get("type") != "quiet_moment_healing_packet":
        raise ValueError("not a quiet moment healing packet")
    if packet.get("schema_version") != "nexus_quiet_moment_healing_packet.v1":
        raise ValueError("unsupported quiet moment healing packet schema")
    event = packet.get("event")
    if not isinstance(event, dict) or event.get("schema_version") != "nexus_quiet_moment.v1":
        raise ValueError("invalid quiet moment event")
    return {
        "schema_version": "nexus_quiet_moment_report_entry.v1",
        "evidence_id": str(packet.get("evidence_id") or ""),
        "reason": str(event.get("reason") or ""),
        "affected_nodes": list(event.get("affected_nodes") or []),
        "resume_after_seconds": int(event.get("resume_after_seconds") or 0),
        "production_writes_allowed": False,
        "allowed_actions": list(event.get("allowed_actions") or []),
    }
