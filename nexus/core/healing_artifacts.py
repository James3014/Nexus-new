from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from nexus.core.belief_contracts import HealingArtifact


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
