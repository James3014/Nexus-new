from __future__ import annotations

import json
import re
from typing import Any

from nexus.research.isolation_contracts import ContaminationGuardResult, ResearchReceipt, ResearchIsolationLevel
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
    "fix",
    "patch",
    "modify",
    "change",
)


def evaluate_research_contamination(payload: dict[str, Any]) -> ContaminationGuardResult:
    """檢查研究產物是否包含設計意圖、實作建議或最終需求外推 (Contamination Check)"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    detected = [term for term in DESIGN_TERMS if re.search(r'\b' + re.escape(term) + r'\b', blob, re.IGNORECASE)]
    if has_design_fields(payload):
        detected.append("design_field")
    detected = list(dict.fromkeys(detected))
    
    # 這裡可以加入更多精確的啟發式檢查
    if detected:
        return ContaminationGuardResult(
            passed=False,
            detected_terms=tuple(detected),
            failure_reason="research_contamination_detected",
        )
    return ContaminationGuardResult()


def build_research_receipt(
    *,
    policy_level: ResearchIsolationLevel,
    brief_masked: bool,
    facts_payload: dict[str, Any] | None,
    artifact_refs: tuple[str, ...] = (),
) -> ResearchReceipt:
    """建構 Phase 6 治理收據，執行 Fail-Closed 判定"""
    
    facts_present = bool(facts_payload and any(facts_payload.values()))
    
    # 執行污染檢查
    guard_res = evaluate_research_contamination(facts_payload or {})
    contamination_detected = not guard_res.passed
    
    # Fail-Closed Gate 判定
    # L2 模式下：必須有 masked brief, 必須有事實產物, 且不得有污染
    gate_passed = True
    if policy_level == ResearchIsolationLevel.L2:
        if not brief_masked or not facts_present or contamination_detected:
            gate_passed = False
    elif policy_level == ResearchIsolationLevel.L1:
        if contamination_detected:
            gate_passed = False

    return ResearchReceipt(
        policy_level=policy_level.value,
        brief_masked=brief_masked,
        facts_artifact_present=facts_present,
        contamination_detected=contamination_detected,
        gate_passed=gate_passed,
        design_terms_detected=guard_res.detected_terms,
        artifact_refs=artifact_refs,
    )
