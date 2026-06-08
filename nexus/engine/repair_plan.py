import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class RepairPlan:
    touched_symbols: List[str] = field(default_factory=list)
    preserved_invariants: List[str] = field(default_factory=list)
    operator_behavior_delta: str = ""
    root_cause_hypothesis: str = ""
    def to_dict(self) -> Dict[str, Any]: return asdict(self)
    @classmethod
    def from_dict(cls, d: Dict[str, Any]): return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
    def format_as_prompt(self) -> str:
        return f"### [Repair Plan Requirements]\nOutput a JSON object with: touched_symbols, preserved_invariants, operator_behavior_delta, root_cause_hypothesis.\n"
