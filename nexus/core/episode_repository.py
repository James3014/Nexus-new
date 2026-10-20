from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
from .memory_coordinator import MemoryCoordinator
from .state_root import state_read_only


class EpisodeRepository:
    """Persistence boundary for episodic memory."""

    def __init__(self, project_root: str, coordinator: MemoryCoordinator | None = None):
        self.root = Path(project_root)
        self.episode_file = self.root / ".nexus" / "knowledge" / "episodic_memory.jsonl"
        self.coordinator = coordinator or MemoryCoordinator()

    def append(self, episode: Dict[str, Any]) -> Path:
        if state_read_only():  # #2721: nothing appended; callers ignore the path
            return self.episode_file
        self.episode_file.parent.mkdir(parents=True, exist_ok=True)
        with self.coordinator.lock(self.episode_file):
            with self.episode_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(episode, ensure_ascii=False) + "\n")
        return self.episode_file
