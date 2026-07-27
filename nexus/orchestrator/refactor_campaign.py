"""Checkpointed multi-wave refactor campaigns built on competition and integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Optional, Sequence
import subprocess

from nexus.executors.worker_contract import SUPPORTED_WORKER_PROVIDERS
from nexus.orchestrator.worker_competition import WorkerCompetitionCoordinator


_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class RefactorWave:
    wave_id: str
    objective: str
    allowed_files: tuple[str, ...]
    verifier_commands: tuple[str, ...] = ()

    def validate(self, max_scope_entries: int) -> None:
        if not self.wave_id or not self.objective.strip():
            raise ValueError("wave_id and objective are required")
        if not self.allowed_files or len(self.allowed_files) > max_scope_entries:
            raise ValueError("wave scope must be non-empty and bounded")
        for path in self.allowed_files:
            if not path or path.startswith("/") or ".." in path.split("/"):
                raise ValueError(f"invalid wave scope path: {path}")


class RefactorCampaignCoordinator:
    def __init__(self, competition: WorkerCompetitionCoordinator, state_dir: Optional[str | Path] = None):
        self.competition = competition
        configured = state_dir or (competition.state_dir.parent / "campaigns")
        self.state_dir = Path(configured).expanduser().resolve()

    def _path(self, campaign_id: str) -> Path:
        return self.state_dir / f"{campaign_id}.json"

    def _write(self, state: Mapping[str, Any]) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        destination = self._path(str(state["campaign_id"]))
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.state_dir, prefix=f".{destination.stem}.", suffix=".tmp", delete=False
        ) as handle:
            json.dump(dict(state), handle, sort_keys=True, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(destination)
        return dict(state)

    def _read(self, campaign_id: str) -> Optional[dict[str, Any]]:
        path = self._path(campaign_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def create(
        self,
        campaign_id: str,
        base_request: Mapping[str, Any],
        waves: Sequence[RefactorWave],
        providers: Sequence[str],
        *,
        max_scope_entries: int = 100,
    ) -> dict[str, Any]:
        safe_id = _SAFE.sub("-", str(campaign_id)).strip("-")
        normalized = tuple(str(provider).strip().lower() for provider in providers)
        if not safe_id:
            raise ValueError("campaign_id must contain a safe identifier")
        if len(normalized) < 2 or len(set(normalized)) != len(normalized):
            raise ValueError("campaign requires at least two distinct providers")
        if set(normalized) - set(SUPPORTED_WORKER_PROVIDERS):
            raise ValueError("campaign contains an unknown provider")
        if not waves:
            raise ValueError("campaign requires at least one wave")
        seen: set[str] = set()
        for wave in waves:
            wave.validate(max_scope_entries)
            if wave.wave_id in seen:
                raise ValueError(f"duplicate wave_id: {wave.wave_id}")
            seen.add(wave.wave_id)
        if self._read(safe_id) is not None:
            raise ValueError(f"campaign already exists: {safe_id}")
        state = {
            "schema": "nexus.refactor_campaign_state.v1",
            "campaign_id": safe_id,
            "status": "READY",
            "provider_order": list(normalized),
            "base_request": dict(base_request),
            "integration_branch": f"nexus/integration/{safe_id}",
            "waves": [asdict(wave) for wave in waves],
            "current_wave_index": 0,
            "current_competition_id": None,
            "completed_waves": [],
            "checkpoints": {},
        }
        return self._write(state)

    def get(self, campaign_id: str) -> Optional[dict[str, Any]]:
        return self._read(campaign_id)

    def advance(self, campaign_id: str) -> dict[str, Any]:
        state = self._read(campaign_id)
        if state is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        if state["status"] in {"COMPLETED", "ROLLED_BACK"}:
            return state
        if state["status"] in {"READY", "WAVE_COMPLETE"}:
            index = int(state["current_wave_index"])
            if index >= len(state["waves"]):
                state["status"] = "COMPLETED"
                return self._write(state)
            wave = RefactorWave(**state["waves"][index])
            request = dict(state["base_request"])
            request.update(
                {
                    "task_id": f"{state['campaign_id']}-{wave.wave_id}",
                    "competition_id": f"{state['campaign_id']}-{wave.wave_id}",
                    "what": wave.objective,
                    "allowed_files": list(wave.allowed_files),
                    "worker": state["provider_order"][0],
                }
            )
            if wave.verifier_commands:
                request["verifier_commands"] = list(wave.verifier_commands)
            competition_state = self.competition.submit(request, state["provider_order"])
            state["status"] = "WAVE_RUNNING"
            state["current_competition_id"] = competition_state["competition_id"]
            state["checkpoints"][wave.wave_id] = state["base_request"].get("target_base_revision")
            return self._write(state)

        if state["status"] != "WAVE_RUNNING":
            raise RuntimeError(f"unsupported campaign status: {state['status']}")
        competition_state = self.competition.get(str(state["current_competition_id"]))
        if competition_state is None:
            raise RuntimeError("current competition state is missing")
        if competition_state["status"] == "WINNER_SELECTED":
            competition_state = self.competition.integrate_winner(
                str(state["current_competition_id"]),
                integration_branch=state["integration_branch"],
            )
        if competition_state["status"] != "INTEGRATED":
            return self._write(state)
        integration = competition_state["integration"]
        state["completed_waves"].append(state["waves"][int(state["current_wave_index"])]["wave_id"])
        state["base_request"]["target_base_revision"] = integration["integration_commit_sha"]
        state["current_wave_index"] = int(state["current_wave_index"]) + 1
        state["current_competition_id"] = None
        state["status"] = "COMPLETED" if state["current_wave_index"] >= len(state["waves"]) else "WAVE_COMPLETE"
        return self._write(state)

    def rollback(self, campaign_id: str, *, wave_id: str) -> dict[str, Any]:
        state = self._read(campaign_id)
        if state is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        checkpoint = state.get("checkpoints", {}).get(wave_id)
        if not checkpoint or not _SHA.fullmatch(str(checkpoint)):
            raise RuntimeError("wave checkpoint is missing or invalid")
        branch = str(state["integration_branch"])
        repo_root = Path(str(state["base_request"]["controller_repo_root"])).expanduser().resolve()
        integration_root = Path(str(state["base_request"]["target_worktree_root"])).expanduser().resolve() / "campaign-rollbacks"
        integration_root.mkdir(parents=True, exist_ok=True)
        path = integration_root / f"{state['campaign_id']}-{wave_id}"
        if path.exists():
            raise RuntimeError("rollback worktree path already exists")
        subprocess.run(["git", "worktree", "add", str(path), branch], cwd=repo_root, capture_output=True, text=True, check=True)
        try:
            subprocess.run(["git", "reset", "--hard", str(checkpoint)], cwd=path, capture_output=True, text=True, check=True)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo_root, capture_output=True, text=True, check=True)
        state["status"] = "ROLLED_BACK"
        state["rolled_back_to"] = checkpoint
        return self._write(state)
