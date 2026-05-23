from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.context_text_store")

DEFAULT_PROGRAM_RULES = "# Default: Optimize target file, metric FlashJudge > prev_score"


class ContextTextStore:
    """Local text and JSON fallbacks for ContextHub facade reads."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def load_program_rules(self, md_path: str = "program.md") -> str:
        path = Path(md_path)
        if not path.exists():
            return DEFAULT_PROGRAM_RULES
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            return f"# Error loading rules: {exc}"

    def load_last_handoff(self) -> dict[str, Any]:
        handoff_path = self.project_root / ".nexus" / "state" / "last_handoff.json"
        if not handoff_path.exists():
            return {}
        try:
            return json.loads(handoff_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("ContextHub failed to load handoff: %s", exc)
            return {}
