from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from nexus.contracts.learning_experience import load_promoted_learning_policy


class LearningPolicyStore(Protocol):
    """Storage seam for runtime learning policy payloads."""

    def read_promoted_policy(self, path: Path) -> dict[str, Any]:
        """Read a promoted policy payload from ``path``."""

    def read_json_policy(self, path: Path) -> dict[str, Any]:
        """Read a plain JSON policy payload from ``path``."""


@dataclass(frozen=True)
class JsonLearningPolicyStore:
    """Default filesystem-backed policy store."""

    def read_promoted_policy(self, path: Path) -> dict[str, Any]:
        return load_promoted_learning_policy(path)

    def read_json_policy(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}


DEFAULT_LEARNING_POLICY_STORE = JsonLearningPolicyStore()
