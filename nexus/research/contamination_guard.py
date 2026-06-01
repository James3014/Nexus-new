from __future__ import annotations

import json
import re
from typing import Any

from nexus.research.isolation_contracts import ContaminationGuardResult
from nexus.research.research_facts import has_design_fields


DESIGN_TERMS = (
    "recommend",
    "recommended",
    "should change",
    "should modify",
    "implement",
    "fix by",
    "patch plan",
    "建議",
    "應該改",
    "實作",
    "修法",
)


def evaluate_research_contamination(payload: dict[str, Any]) -> ContaminationGuardResult:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    detected = [term for term in DESIGN_TERMS if re.search(re.escape(term), blob, re.IGNORECASE)]
    if has_design_fields(payload):
        detected.append("design_field")
    detected = list(dict.fromkeys(detected))
    if detected:
        return ContaminationGuardResult(
            passed=False,
            detected_terms=tuple(detected),
            failure_reason="research_contamination",
        )
    return ContaminationGuardResult()
