"""
StrategyEnvelope v1: Schema-only skeleton for StraTA strategy planning.
Not connected to execution. Not connected to CampaignGeneral/SurgicalPacker/prompt_builder.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional


STRATEGY_ENVELOPE_SCHEMA = "nexus.strategy.strategy_envelope.v1"

REQUIRED_FIELDS = [
    "schema",
    "strategy_id",
    "task_goal",
    "bug_hypothesis",
    "repair_strategy",
    "target_symbols",
    "allowed_paths",
    "forbidden_paths",
    "context_budget_tokens",
    "invariants",
    "abort_conditions",
    "created_by",
    "created_at",
]


@dataclass
class StrategyEnvelope:
    """StrategyEnvelope v1 — schema-only, no execution."""
    schema: str = STRATEGY_ENVELOPE_SCHEMA
    strategy_id: str = ""
    task_goal: str = ""
    bug_hypothesis: str = ""
    repair_strategy: str = ""
    target_symbols: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    forbidden_paths: List[str] = field(default_factory=list)
    context_budget_tokens: int = 0
    invariants: List[str] = field(default_factory=list)
    abort_conditions: List[str] = field(default_factory=list)
    created_by: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.strategy_id:
            self.strategy_id = self._compute_id()

    def _compute_id(self) -> str:
        """Compute strategy_id from content hash."""
        content = json.dumps({
            "task_goal": self.task_goal,
            "bug_hypothesis": self.bug_hypothesis,
            "repair_strategy": self.repair_strategy,
            "target_symbols": sorted(self.target_symbols),
            "allowed_paths": sorted(self.allowed_paths),
            "forbidden_paths": sorted(self.forbidden_paths),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def validate(self) -> List[str]:
        """Validate the envelope. Returns list of errors (empty = valid)."""
        errors = []
        for field_name in REQUIRED_FIELDS:
            val = getattr(self, field_name, None)
            if val is None or val == "":
                errors.append(f"missing_required_field: {field_name}")
            if field_name == "context_budget_tokens" and val == 0:
                errors.append("context_budget_tokens must be > 0")
        return errors

    def is_valid(self) -> bool:
        """Check if the envelope is valid."""
        return len(self.validate()) == 0

    def check_paths(self, file_path: str) -> bool:
        """Check if a file path is allowed (not forbidden)."""
        for fp in self.forbidden_paths:
            if file_path.startswith(fp):
                return False
        if self.allowed_paths:
            return any(file_path.startswith(ap) for ap in self.allowed_paths)
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyEnvelope":
        return cls(**{k: v for k, v in data.items() if k in REQUIRED_FIELDS})

    @classmethod
    def from_json(cls, json_str: str) -> "StrategyEnvelope":
        return cls.from_dict(json.loads(json_str))
