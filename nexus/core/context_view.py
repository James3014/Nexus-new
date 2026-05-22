from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class StateView:
    metadata: Dict[str, Any]
    conversation_metadata: Dict[str, Any] | None = None
    route_receipts: List[Dict[str, Any]] | None = None
    report_receipts: List[Dict[str, Any]] | None = None

    def get_conversation_metadata(self) -> Dict[str, Any]:
        return dict(self.conversation_metadata or {})

    def receipt_summary(self) -> Dict[str, int]:
        receipts = list(self.route_receipts or []) + list(self.report_receipts or [])
        return {
            "selected": sum(1 for item in receipts if isinstance(item, dict) and item.get("selected")),
            "invoked": sum(1 for item in receipts if isinstance(item, dict) and item.get("invoked")),
            "evidence": sum(1 for item in receipts if isinstance(item, dict) and item.get("evidence_present")),
            "gate": sum(1 for item in receipts if isinstance(item, dict) and item.get("gate_passed")),
        }


@dataclass(frozen=True)
class ContextDependencies:
    memory_service: Any | None = None
    wisdom_vault: Any | None = None
    belief_engine: Any | None = None
    knowledge_injector: Any | None = None
    prompt_builder: Any | None = None
