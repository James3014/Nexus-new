from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Sequence

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


_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad]")
_WORD_HYPHEN = re.compile(r"(?<=[A-Za-z])[\-\u2010-\u2015](?=[A-Za-z])")
_INLINE_SPACE = re.compile(r"[ \t\r\f\v]+")


def normalize_research_text(text: str) -> str:
    """NFKC (full-width -> ASCII), drop zero-width/soft-hyphen, word-hyphen -> space, collapse
    inline whitespace.  Newlines are kept so line-start labels and diff lines still match."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _WORD_HYPHEN.sub(" ", text)
    return _INLINE_SPACE.sub(" ", text)


def _echo_spans(text: str, echoes: Sequence[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    lowered = text.lower()
    for echo in echoes:
        start = lowered.find(echo)
        while echo and start >= 0:
            spans.append((start, start + len(echo)))
            start = lowered.find(echo, start + 1)
    return spans


def find_design_matches(
    text: str,
    patterns: Sequence[tuple[str, re.Pattern[str]]],
    *,
    echo_texts: Sequence[str] = (),
) -> list[str]:
    """Labels of ``patterns`` found in ``text``.

    A match is ignored only when it lies entirely inside an echo of the task/query and that
    echo is itself free of design patterns.  An echo that carries design language is never
    discounted, and a match that crosses an echo boundary still counts.
    """
    norm = normalize_research_text(text)
    clean_echoes = []
    for echo in echo_texts:
        echo_norm = normalize_research_text(str(echo)).strip().lower()
        if echo_norm and not any(pattern.search(echo_norm) for _, pattern in patterns):
            clean_echoes.append(echo_norm)
    spans = _echo_spans(norm, clean_echoes)
    found: list[str] = []
    for label, pattern in patterns:
        for match in pattern.finditer(norm):
            if not any(lo <= match.start() and match.end() <= hi for lo, hi in spans):
                found.append(label)
                break
    return found


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _strings(item)]
    return []


def evaluate_research_contamination(
    payload: dict[str, Any],
    *,
    patterns: Sequence[tuple[str, re.Pattern[str]]] | None = None,
    echo_texts: Sequence[str] = (),
) -> ContaminationGuardResult:
    """檢查研究產物是否包含設計意圖、實作建議或最終需求外推 (Contamination Check)

    ``patterns`` (label, compiled regex) replaces the single-word DESIGN_TERMS for one call
    site (P-CONTAM-01 live research routes, #2199/#2216); each string of the payload (keys
    included) is matched separately after normalisation, with clean task/query echoes
    discounted.  The default keeps the original single-word matching unchanged.
    """
    if patterns is None:
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        detected = [term for term in DESIGN_TERMS if re.search(r'\b' + re.escape(term) + r'\b', blob, re.IGNORECASE)]
    else:
        detected = [
            label for text in _strings(payload) for label in find_design_matches(text, patterns, echo_texts=echo_texts)
        ]
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
