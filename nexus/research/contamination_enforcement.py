"""P-CONTAM-01 record-only contamination signal on live research routes (#2199, #2216).

One check shared by every route that accepts research output: the canonical research
executor (``nexus/core/capability_executor_registry.py``) and the research auto-flow
(``nexus/app/research_flow_service.py``).  Owner decision (option B, 2026-10-15): the
routes RECORD the signal and do NOT block; held-out detection was 53/120 (44%), below the
70% bar for blocking.  Upgrading to block is a later Owner decision based on the recorded
signals (``<workspace>/.nexus/research/contamination_signals.jsonl``).

- Walks the research output: strings, dict keys (as text), lists/tuples/sets, bytes
  (UTF-8), dataclasses, pydantic models (``model_dump``) and plain objects (``vars``).
  Design-field names (``DESIGN_FIELD_NAMES``) are detected at any depth, in keys and in
  object attribute names.  Any other object type cannot be inspected, so the check fails
  closed instead of scanning ``str(obj)``.
- Calls the contamination guard with ``CANONICAL_DESIGN_PATTERNS``: structural patterns
  for design proposals (modal + design verb, "the fix/plan/solution is to", labelled
  prefixes such as "Fix:" or "Proposed change:", "can be fixed by", "we recommend",
  diff hunks, and Chinese equivalents) instead of the guard's legacy single words.
- Task/query echoes are discounted only when the echo itself has no design pattern and the
  match lies fully inside it.

The verdict is ``RESEARCH_CONTAMINATION_DETECTED`` on a hit and
``RESEARCH_CONTAMINATION_GUARD_ERROR`` (detected unknown) when the check cannot run.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
import enum
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

POLICY_ID = "P-CONTAM-01"
REASON_DETECTED = "RESEARCH_CONTAMINATION_DETECTED"
REASON_GUARD_ERROR = "RESEARCH_CONTAMINATION_GUARD_ERROR"

# Design verbs (stems).  _V is broad (after "recommend ...ing"/"consider ...ing"); _DV is
# the narrower set used after modal verbs.
_V = r"(?:refactor|replac|add|remov|delet|chang|us|switch|renam|rewrit|modif|updat|mov|introduc|implement|wrap|split|extract|migrat|convert|drop|patch|fix|adjust|increas|decreas|rais|lower|bump|clamp|guard|catch|handl|avoid|adopt|swap|redesign|restructur|reorganiz|merg|inlin|deprecat|disabl|enabl|set|mak|call|pass|return|check|validat|instead|insert|append|prepend|replac|cach|retry|limit|throttl|lock|initializ|configur|expos|hid|export|import|rais|throw|log|emit|reject|accept|skip|filter|sort|normaliz|escap|sanitiz|pin|upgrad|downgrad|install|uninstall|creat|build|defin|declar|overrid|extend|subclass|inject|mock|stub|bound|cap)"
_VE = _V + r"\w*"
_DV = r"(?:refactor|replac|add|remov|delet|chang|us|switch|renam|rewrit|modif|updat|mov|introduc|implement|wrap|split|extract|migrat|convert|drop|patch|fix|adjust|increas|decreas|bump|clamp|guard|catch|swap|redesign|restructur|adopt|consider|avoid|insert|reorder|batch|cach|retry|lock|pin|upgrad|downgrad|throttl|debounc|memoiz|parametriz|inject|overrid|skip|check|validat|return|set|ignor|filter|handl|reject|defer|reset|clos|releas|escap|sanitiz|acquir|normalis|normaliz|keep|mak|call|gate|default|shorten|lengthen|rais|lower|increas|decreas)"
_DVE = _DV + r"\w*"
_PATTERN_SOURCES: tuple[tuple[str, str], ...] = (
    (
        "modal_design",
        r"\b(?:we|you|i|one|they|developers?|the developer|the team|maintainers?|callers?|the caller|users?)\s+(?:should|could|ought to|must|need to|have to|might want to|may want to|had better|would do well to|can)\s+(?:also\s+|probably\s+|instead\s+|just\s+|really\s+|first\s+|simply\s+|now\s+|then\s+|definitely\s+)?"
        + _DVE
        + r"\b|\b(?:it\'?s|it is|it would be|would be)\s+better\s+to\s+"
        + _DVE
        + r"\b",
    ),
    (
        "solution_is",
        r"\b(?:the|a|one|our|my|best|better|simplest|cleanest|right|correct|proper|real|easiest|recommended|proposed|suggested|only|safest|obvious|quickest|ideal)\s+(?:\w+\s+){0,2}?(?:solution|plan|approach|remedy|fix|answer|idea|proposal|recommendation|suggestion|workaround|way forward|way out|option|design|resolution|patch|change|move|step|course of action|thing to do|bet|way to go|advice|practice|remediation|strategy|direction|route|path forward)\s+(?:here\s+|then\s+)?(?:is|would be|will be|is simply|would simply be|might be|could be)\s+(?:to\b|that\b|:|a\s+one|(?:upgrading|replacing|adding|switching|moving|using|removing|splitting|wrapping|dropping|migrating|rewriting|refactoring|introducing|caching|disabling|enabling|pinning)\b)",
    ),
    (
        "label_prefix",
        r"(?:^|\n|[.!?;。！？；]\s*|\n\s*[-*>#\d.)]+\s*)(?:the\s+|my\s+|our\s+|a\s+)?(?:fix|patch|proposed (?:change|fix|patch|solution|approach|design|plan)|recommended (?:change|fix|patch|solution|approach|action)|recommendations?|solution|better|alternative|suggestions?|suggested (?:change|fix|patch|approach|design)|proposal|remedy|workaround|next steps?|todo|action items?|quick win|improvement|(?:implementation|patch|migration|remediation|fix|action) plan)\s*(?:[:：]|\s[—–]\s)",
    ),
    (
        "fixed_by",
        r"\b(?:can|could|may|might|should|would|will)\s+(?:easily\s+|simply\s+)?be\s+(?:fixed|resolved|solved|addressed|avoided|mitigated|corrected|repaired|remedied|prevented|handled)\s+by\b",
    ),
    (
        "to_resolve",
        r"\bto\s+(?:fix|resolve|solve|address|work around|mitigate|correct|remedy|repair|avoid|prevent)\s+(?:this|it|that|these|the\s+(?:\w+\s+)?(?:issue|bug|problem|error|failure|regression|crash|race|leak|deadlock|timeout))\b\s*,\s*\w+",
    ),
    (
        "we_recommend",
        r"\b(?:we|i|i'?d|i would|we'?d|we would|i'?m|we are|we're|i strongly|we strongly|i would strongly|we would strongly)\s+(?:strongly\s+|would\s+)?(?:recommend|suggest|propose|advise|advocate)\w*\b",
    ),
    (
        "recommend_gerund",
        r"\b(?:recommend|suggest|propose|advise)(?:s|ing)?\s+(?:that\s+(?:we|you|the)\b|"
        + _V
        + r"\w*ing\b|to\s+"
        + _VE
        + r"\b)",
    ),
    (
        "it_is_recommended",
        r"\b(?:it\s+is|it'?s|it\s+would\s+be)\s+(?:strongly\s+|highly\s+)?(?:recommended|advisable|advised|suggested|preferable|better|best|wise)\s+(?:to|that)\b",
    ),
    ("consider_gerund", r"\bconsider\s+" + _V + r"\w*ing\b"),
    (
        "better_design",
        r"\b(?:a\s+)?(?:better|cleaner|simpler|safer|more robust)\s+(?:design|approach|solution|option|fix|implementation|way)\s+(?:would|is|might|could)\b",
    ),
    (
        "gerund_would_fix",
        r"\b(?:replacing|adding|switching|moving|changing|using|wrapping|removing|bumping|caching|introducing|splitting|raising|lowering|pinning|upgrading|catching|guarding|clamping|validating|checking|skipping|making|setting)\b[^.\n]{1,80}\b(?:would|should|will|could|might)\s+(?:fix|solve|resolve|address|eliminate|prevent|avoid|remove|cure)\b",
    ),
    (
        "needs_to",
        r"\b(?:needs?|has|have)\s+to\s+(?:be\s+)?(?:refactor|replac|rewrit|modif|updat|chang|patch|fix|renam|migrat|redesign)\w*\b",
    ),
    (
        "change_from_to",
        r"\b(?:change|switch|convert|bump|raise|lower)\s+[^\n]{1,60}?\s+from\s+[^\n]{1,60}?\s+to\s+\S",
    ),
    (
        "imperative_start",
        r"(?:^|\n|[.!?;。！？]\s+)\s*(?:[-*]\s+)?(?:implement|introduce|redesign)\s+(?:a|an)\s+",
    ),
    ("diff_hunk", r"(?:^|\n)@@ -\d+(?:,\d+)? \+\d+|(?:^|\n)--- a/\S+\s*\n\+\+\+ b/"),
    (
        "diff_lines",
        r"(?:^|\n)-(?!-)[^\n]*\n(?:[- ][^\n]*\n)*\+(?!\+)\S?|(?:^|\n)\+(?!\+)[^\n]*\n(?:[+ ][^\n]*\n)*-(?!-)",
    ),
    (
        "design_plan",
        r"\b(?:recommend|suggest|propose|draft|write|prepare|here is|here's|following)\w*\s+(?:a|an|the|this|our|my)\s+(?:\w+\s+)?(?:patch|implementation|migration|remediation|fix|refactor(?:ing)?)\s+plan\b",
    ),
    (
        "passive_should",
        r"\b(?:should|ought to|must|needs? to|would ideally|would better)\s+(?:really\s+|probably\s+|ideally\s+)?be\s+(?:split|rewritten|refactored|replaced|moved|changed|removed|renamed|extracted|migrated|converted|dropped|deprecated|deleted|redesigned|restructured|wrapped|cached|memoized|reworked|simplified|merged|inlined|swapped|consolidated|decoupled|parameterized|batched)\b",
    ),
    (
        "ought_better",
        r"\bought to\s+\w+|\b(?:be|is|are)\s+better off\s+\w+ing\b|\bit makes (?:more |the most )?sense to\s+"
        + _DVE
        + r"\b|\bbest practice (?:here )?(?:is|would be) to\b",
    ),
    (
        "first_person_would",
        r"\b(?:i|we)\s+would\s+(?:\w+\s+)?"
        + _DVE
        + r"\b|\bif i were you\b|\bin my (?:opinion|view)\b[^.\n]{0,80}\b(?:should|would|could)\b|\blet'?s\s+"
        + _DVE
        + r"\b",
    ),
    (
        "use_instead",
        r"\buse\s+[^\s.,]{1,40}\s+instead of\b|\binstead of\s+[^.\n]{1,60},\s*(?:use|call|switch to|try)\b",
    ),
    (
        "np_modal",
        r"\b(?:the|this|that|your|our)\s+(?:\w+\s+){0,2}(?:should|ought to|needs to|has to)\s+(?:\w+ly\s+)?"
        + _DVE
        + r"\b|\byou(?:'ll| will|'d| would)?\s+(?:want|need) to\s+"
        + _DVE
        + r"\b",
    ),
    (
        "fix_by_requires",
        r"\b(?:fix|resolv|address)\w*\s+(?:this|it|that)\s+(?:is\s+)?(?:by|requires|would require)\b|\bone way to (?:fix|solve|resolve|address|avoid)\b|\bworth\s+"
        + _V
        + r"\w*ing\b|\bit would make sense to\b|\b(?:i'?d|we'?d|i would|we would)\s+go with\b",
    ),
    (
        "imperative_purpose",
        r"(?:^|\n|[.!?]\s+)\s*(?:[-*]\s+)?(?:add|make|use|rewrite|move|change|replace|wrap|acquire|convert|normalise|normalize|cache|pin|bump|drop|keep|switch|guard)\b[^.\n]{1,100}?\b(?:to (?:avoid|prevent|fix|eliminate|stop)|so (?:that|the|it) (?:is|are|always|never|no longer))\b",
    ),
    # Chinese
    (
        "zh_suggest",
        r"建議(?:您|你|我們)?(?:將|把|改|重構|更換|調整|刪除|修改|新增|加入|加上|使用|採用|移除|替換|實作|拆分|增加|直接|換|補上|導入|引入|升級|降級|關閉|開啟|設定|設為|重寫)",
    ),
    (
        "zh_solution",
        r"(?:解法|解決方案|解決方法|解決辦法|修正方式|修正方法|修復方式|修復方法|修法|改法|改善方式|改進方式|修補方式|對策|(?:比較好|更好|較好|正確|建議|理想|合理)的(?:做法|作法|方式|方法|處理方式))(?:是|為|就是|：|:|如下)",
    ),
    (
        "zh_should",
        r"(?:應該|應當|最好|宜|可以考慮|可考慮|不妨|考慮)(?:要|先|直接|再)?(?:把|將|改|重構|修改|換|移除|刪除|新增|加上|加入|調整|使用|採用|改用|替換|拆分|重寫|補上|移到|移至|搬到)|需要(?:修改|重構|調整|替換|改寫|改成|改為|改用)|可以(?:把|將)",
    ),
    (
        "zh_via",
        r"(?:可以|能夠|能)(?:透過|藉由|經由)[^。\n]{1,30}(?:來)?(?:解決|修正|修復|避免|改善|處理)",
    ),
    (
        "zh_label",
        r"(?:^|\n|[。！？；]\s*)(?:方案|下一步|建議|修正|修改|改法|解法|做法|處理)\s*[：:]",
    ),
    ("zh_we", r"我們(?:應該|應當|建議|最好|可以考慮|不妨)"),
    (
        "zh_would",
        r"(?:可以|可|能)(?:改寫|改成|改為|改用|換成|重構|拆成|拆分成|調成|調整成)|(?:我|我們)(?:會|會比較)?建議|應(?:改|換|移|拆|重構|刪除|移除)|需要(?:把|將)|(?:就能|即可|就可以)(?:解決|修正|修復|避免)",
    ),
    (
        "zh_label2",
        r"(?:建議做法|修改建議|改進方向|改善建議|優化建議|處理方式|解決辦法|改善方向|最佳做法|最佳作法|推薦做法)(?:是|為|：|:)",
    ),
    (
        "zh_method",
        r"(?:解決|修正|修復|修改|處理|改善|修)的?(?:方法|方式|辦法|做法|作法|建議)(?:是|為|如下|：|:)|(?:修正|修改|下一步|改善|優化)建議\s*[：:]|應該要|需要(?:重寫|重新設計|拆分|改|新增|移除|刪除)|(?:改成|改為|換成|改用)[^。\n]{1,30}(?:就|即可|才)(?:不會|能|可以)|可以解決[^。\n]{0,12}問題",
    ),
)


CANONICAL_DESIGN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(source, re.IGNORECASE | re.MULTILINE)) for label, source in _PATTERN_SOURCES
)

_MAX_NODES = 200_000
_MAX_DEPTH = 64
_SCALARS = (int, float, bool, decimal.Decimal, _dt.date, _dt.time, _dt.timedelta, uuid.UUID)


class UninspectableResearchOutput(TypeError):
    """Research output holds an object the check cannot read; fail closed."""


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


class _Walker:
    def __init__(self) -> None:
        from nexus.research.research_facts import DESIGN_FIELD_NAMES

        self.design_fields = DESIGN_FIELD_NAMES
        self.texts: list[str] = []
        self.fields: set[str] = set()
        self.nodes = 0
        self.active: set[int] = set()

    def name(self, key: Any, depth: int) -> None:
        if isinstance(key, str) and key in self.design_fields:
            self.fields.add(key)
        self.walk(key, depth)

    def walk(self, value: Any, depth: int = 0) -> None:
        self.nodes += 1
        if self.nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise UninspectableResearchOutput("research output too large or too deep to scan")
        if value is None or isinstance(value, _SCALARS):
            return
        if isinstance(value, str):
            self.texts.append(value)
            return
        if isinstance(value, (bytes, bytearray, memoryview)):
            self.texts.append(bytes(value).decode("utf-8", errors="replace"))
            return
        if isinstance(value, enum.Enum):
            self.walk(value.value, depth + 1)
            return
        if isinstance(value, os.PathLike):
            self.walk(os.fspath(value), depth + 1)
            return
        marker = id(value)
        if marker in self.active:
            return  # cycle: this container is already being scanned
        self.active.add(marker)
        try:
            self._walk_container(value, depth)
        finally:
            self.active.discard(marker)

    def _walk_container(self, value: Any, depth: int) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                self.name(key, depth + 1)
                self.walk(item, depth + 1)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                self.walk(item, depth + 1)
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                self.name(field.name, depth + 1)
                self.walk(getattr(value, field.name, None), depth + 1)
        elif callable(getattr(value, "model_dump", None)) and not isinstance(value, type):
            dumped = value.model_dump()
            if not isinstance(dumped, Mapping):
                raise UninspectableResearchOutput(
                    f"model_dump of {type(value).__name__} is not a mapping"
                )
            self.walk(dumped, depth + 1)
        elif hasattr(value, "__dict__") and not isinstance(value, type) and not callable(value):
            attrs = vars(value)
            for key, item in attrs.items():
                self.name(key, depth + 1)
                self.walk(item, depth + 1)
        else:
            raise UninspectableResearchOutput(
                f"cannot inspect research output of type {type(value).__name__}"
            )


def check_research_output(
    research_output: Any, *, echo_texts: Iterable[str] = ()
) -> ContaminationVerdict:
    """Fail-closed P-CONTAM-01 check of one research output (pack, context, ...)."""
    try:
        from nexus.research import contamination_guard

        walker = _Walker()
        walker.walk(research_output)
        payload: dict[str, Any] = {"research_text": walker.texts}
        for name in sorted(walker.fields):
            payload[name] = True
        guard = contamination_guard.evaluate_research_contamination(
            payload,
            patterns=CANONICAL_DESIGN_PATTERNS,
            echo_texts=tuple(str(text) for text in echo_texts if text),
        )
        if guard.passed is True:
            return ContaminationVerdict(passed=True)
        return ContaminationVerdict(
            passed=False,
            reason=REASON_DETECTED,
            detected_terms=tuple(str(term) for term in guard.detected_terms),
        )
    except Exception:  # fail closed: a broken or blind check never lets research through
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
    "route_cost_policy",
})


RECORD_ONLY = "record_only"
SIGNAL_LOG_RELPATH = (".nexus", "research", "contamination_signals.jsonl")


def signal_from_verdict(verdict: ContaminationVerdict) -> dict[str, Any]:
    """Record-only signal; ``detected`` is None when the check could not run."""
    if verdict.passed:
        detected: bool | None = False
    elif verdict.reason == REASON_DETECTED:
        detected = True
    else:
        detected = None
    return {
        "policy_id": POLICY_ID,
        "mode": RECORD_ONLY,
        "detected": detected,
        "reason": verdict.reason,
        "terms": list(verdict.detected_terms),
    }


def append_contamination_signal(
    log_root: Any, signal: Mapping[str, Any], *, route: str, task_id: Any
) -> None:
    """Append one signal to <log_root>/.nexus/research/contamination_signals.jsonl.

    Best effort: a write failure is logged and never changes the research result.
    """
    import json
    import logging
    from datetime import datetime, timezone
    from pathlib import Path

    try:
        path = Path(log_root).joinpath(*SIGNAL_LOG_RELPATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": "nexus.research.contamination_signal.v1",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "route": route,
            "task_id": str(task_id or ""),
            **dict(signal),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "contamination signal log write failed: %s", str(exc)[:200]
        )


def _research_part(research_context: Any) -> Any:
    if isinstance(research_context, Mapping):
        return {
            str(key): value
            for key, value in research_context.items()
            if str(key) not in FLOW_CONTEXT_PLANNER_KEYS
        }
    return research_context


def record_flow_contamination_signal(
    capability_evidence: dict[str, Any],
    *,
    research_context: Any,
    task_desc: str,
    log_root: Any = None,
    task_id: Any = None,
) -> dict[str, Any]:
    """Research auto-flow: record the P-CONTAM-01 signal; research_gate_passed is unchanged."""
    if not capability_evidence.get("research_used") and not capability_evidence.get(
        "research_gate_passed"
    ):
        return capability_evidence
    signal = signal_from_verdict(
        check_research_output(_research_part(research_context), echo_texts=(task_desc,))
    )
    updated = dict(capability_evidence)
    updated["research_contamination_signal"] = signal
    if log_root is not None:
        append_contamination_signal(
            log_root, signal, route="research_flow_service.run_auto_flow", task_id=task_id
        )
    return updated
