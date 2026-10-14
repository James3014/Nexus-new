"""P-CONTAM-01 enforcement on live research routes (#2199).

One check shared by every route that accepts research output: the canonical research
executor (``nexus/core/capability_executor_registry.py``) and the research auto-flow
(``nexus/app/research_flow_service.py``).  It calls the contamination guard
(``nexus/research/contamination_guard.py``) on every string in the research output, plus
every design field found at any depth.

Matching uses ``CANONICAL_DESIGN_TERMS``: design-proposal phrases, not the generic single
words (fix, patch, change, modify, implement, recommend) of the guard's legacy
``DESIGN_TERMS``.  Those words are ordinary in factual software research text and blocked
most of it.  Text the provider echoes from the task/query is removed before scanning.

Contamination returns ``RESEARCH_CONTAMINATION_DETECTED``; any error in the check returns
``RESEARCH_CONTAMINATION_GUARD_ERROR``.  Both mean the research output is not accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

POLICY_ID = "P-CONTAM-01"
REASON_DETECTED = "RESEARCH_CONTAMINATION_DETECTED"
REASON_GUARD_ERROR = "RESEARCH_CONTAMINATION_GUARD_ERROR"

# Design-proposal phrasing: a research result telling the implementer what to build or
# change.  Measured 2026-10-15 (#2216): 1/500 Nexus-new issue title+body, 30/2660 300-word
# docs chunks, 0/59 historical research packs blocked; 15/15 contamination samples caught.
CANONICAL_DESIGN_TERMS: tuple[str, ...] = (
    "should change",
    "should modify",
    "should be changed",
    "should be modified",
    "should be rewritten",
    "fix by",
    "fix it by",
    "fix this by",
    "the fix is to",
    "patch plan",
    "implementation plan",
    "proposed fix",
    "proposed patch",
    "suggested fix",
    "suggested patch",
    "recommended fix",
    "recommended patch",
    "we recommend",
    "i recommend",
    "i suggest",
    "we suggest",
    "recommend changing",
    "recommend modifying",
    "recommend replacing",
    "recommend implementing",
    "應該改",
    "修法",
    "建議修改",
    "建議改成",
    "建議實作",
)

# Echoes shorter than this are not stripped, so a short task text (for example a bare
# "we recommend") cannot erase the design phrases it contains from the findings.
_MIN_ECHO_CHARS = 24
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ContaminationVerdict:
    passed: bool
    reason: str = ""
    detected_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": POLICY_ID,
            "passed": self.passed,
            "reason": self.reason,
            "detected_terms": list(self.detected_terms),
        }


def _normalise(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _strip_echoes(text: str, echoes: tuple[str, ...]) -> str:
    for echo in echoes:
        text = re.sub(re.escape(echo), " ", text, flags=re.IGNORECASE)
    return text


def _collect(
    value: Any, echoes: tuple[str, ...], texts: list[str], fields: set[str], depth: int = 0
) -> None:
    from nexus.research.research_facts import DESIGN_FIELD_NAMES

    if depth > 32:
        raise ValueError("research output nested too deeply to scan")
    if isinstance(value, str):
        text = _normalise(_strip_echoes(_normalise(value), echoes))
        if text:
            texts.append(text)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in DESIGN_FIELD_NAMES:
                fields.add(name)
            _collect(item, echoes, texts, fields, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _collect(item, echoes, texts, fields, depth + 1)
    elif value is not None and not isinstance(value, (bool, int, float)):
        _collect(str(value), echoes, texts, fields, depth + 1)


def check_research_output(
    research_output: Any, *, echo_texts: Iterable[str] = ()
) -> ContaminationVerdict:
    """Fail-closed P-CONTAM-01 check of one research output (pack, context, ...)."""
    try:
        from nexus.research import contamination_guard

        echoes = tuple(
            sorted(
                {
                    _normalise(str(e))
                    for e in echo_texts
                    if len(_normalise(str(e or ""))) >= _MIN_ECHO_CHARS
                },
                key=len,
                reverse=True,
            )
        )
        texts: list[str] = []
        fields: set[str] = set()
        _collect(research_output, echoes, texts, fields)
        payload: dict[str, Any] = {"research_text": texts}
        for name in sorted(fields):
            payload[name] = True
        guard = contamination_guard.evaluate_research_contamination(
            payload, terms=CANONICAL_DESIGN_TERMS
        )
        if guard.passed is True:
            return ContaminationVerdict(passed=True)
        return ContaminationVerdict(
            passed=False,
            reason=REASON_DETECTED,
            detected_terms=tuple(str(term) for term in guard.detected_terms),
        )
    except Exception:  # fail closed: a broken check never lets research through
        return ContaminationVerdict(passed=False, reason=REASON_GUARD_ERROR)


# Keys of nexus_research_context_v1 that Nexus's own planner writes (route role, the task
# itself as hypothesis, capability recommendations, next-action hint, scores).  They are
# not research output; every other key (doc_scout hits, verified/rejected claims,
# blocked_assumptions, global_constraints, retrieval_refs, unknown keys) is scanned.
FLOW_CONTEXT_PLANNER_KEYS = frozenset({
    "schema",
    "role",
    "hypothesis",
    "risk_flags",
    "recommended_capabilities",
    "next_action_hint",
    "confidence",
    "constraint_lookup_receipt",
})


def enforce_on_flow_evidence(
    capability_evidence: dict[str, Any], *, research_context: Any, task_desc: str
) -> dict[str, Any]:
    """Research auto-flow (research_flow_service.run_auto_flow): no research PASS on contamination."""
    if not capability_evidence.get("research_used") and not capability_evidence.get(
        "research_gate_passed"
    ):
        return capability_evidence
    if isinstance(research_context, Mapping):
        research_output: Any = {
            str(key): value
            for key, value in research_context.items()
            if str(key) not in FLOW_CONTEXT_PLANNER_KEYS
        }
    else:
        research_output = research_context
    verdict = check_research_output(research_output, echo_texts=(task_desc,))
    updated = dict(capability_evidence)
    updated["research_contamination"] = verdict.to_dict()
    if not verdict.passed:
        updated["research_gate_passed"] = False
        updated["research_failure_reason"] = verdict.reason
    return updated
