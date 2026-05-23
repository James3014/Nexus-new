"""Pre-index skill-fit candidate pools without making promotion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

CAPABILITY_RELEVANCE_KEYWORDS = {
    "repair_and_coding": (
        "repair",
        "debug",
        "tdd",
        "refactor",
        "simplification",
        "clean",
    ),
    "governance_and_trust": (
        "acceptance",
        "audit",
        "auth",
        "claim",
        "compliance",
        "evidence",
        "failclosed",
        "gate",
        "governance",
        "hardening",
        "security",
        "trust",
    ),
    "research_and_source_discipline": (
        "citation",
        "context",
        "docs",
        "evidence",
        "research",
        "retrieval",
        "source",
        "synthesis",
    ),
}
CAPABILITY_PREFERRED_SKILLS = {
    "repair_and_coding": (
        "tdd",
        "test-driven-development",
        "wondelai-clean-code",
        "workos-live-preview-debug-loop",
        "python-debugpy",
        "wondelai-refactoring-patterns",
    ),
    "governance_and_trust": (
        "nexus-acceptance-evidence-gate",
        "acceptance-evidence-failclosed",
        "nexus-root-cause-probe",
        "nexus-goal-closure-executor",
        "as-security-and-hardening",
        "audit",
    ),
    "research_and_source_discipline": (
        "browserbase-company-research",
        "arxiv",
        "autoresearch",
        "browserbase-search",
        "gbrain-citation-fixer",
        "authenticated-page-access-handoff",
    ),
}
CAPABILITY_DISCOVERY_BLOCKED_SKILLS = {
    "repair_and_coding": {
        "gstack-codex",
        "improve-codebase-architecture",
        "python-debugpy",
        "systematic-debugging",
        "tdd",
        "workos-live-preview-debug-loop",
        "wondelai-clean-architecture",
        "wondelai-clean-code",
        "wondelai-refactoring-patterns",
        "zoom-out",
    },
}


@dataclass(frozen=True)
class SkillFitCandidateIndex:
    """Query candidate rows through one deterministic selection Module."""

    candidates: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_pool(cls, pool: Mapping[str, Any]) -> "SkillFitCandidateIndex":
        return cls(tuple(row for row in pool.get("candidates", []) or [] if isinstance(row, Mapping)))

    @staticmethod
    def canonical_skill_id(row: Mapping[str, Any]) -> str:
        skill_id = str(row.get("skill_id") or "").strip()
        return skill_id.removeprefix("gstack-")

    def explicit_for_capability(self, capability: str, skill_ids: Iterable[str]) -> list[Mapping[str, Any]]:
        wanted = {str(skill_id).strip() for skill_id in skill_ids if str(skill_id).strip()}
        if not wanted:
            return []
        selected = []
        seen: set[str] = set()
        for row in sorted(self.candidates, key=lambda item: (str(item.get("skill_id") or ""), str(item.get("path") or ""))):
            skill_id = str(row.get("skill_id") or "")
            if skill_id not in wanted or skill_id in seen:
                continue
            if row.get("ablation_eligible") is not True:
                continue
            if capability not in _capability_candidates(row):
                continue
            selected.append(row)
            seen.add(skill_id)
        return selected

    def selected_for_capability(self, capability: str, max_skill_arms: int) -> list[Mapping[str, Any]]:
        matching = sorted(self.matching_for_capability(capability), key=lambda row: self.candidate_sort_key(row, capability))
        runtime = [row for row in matching if row.get("runtime_eligible") is True]
        non_runtime = [row for row in matching if row.get("runtime_eligible") is not True]
        selected: list[Mapping[str, Any]] = []
        selected_skill_ids: set[str] = set()
        if runtime:
            selected.append(runtime[0])
            selected_skill_ids.add(self.canonical_skill_id(runtime[0]))
        for row in non_runtime:
            skill_id = self.canonical_skill_id(row)
            if row in selected or skill_id in selected_skill_ids:
                continue
            selected.append(row)
            selected_skill_ids.add(skill_id)
            if len(selected) >= max_skill_arms:
                break
        for row in runtime[1:]:
            if len(selected) >= max_skill_arms:
                break
            skill_id = self.canonical_skill_id(row)
            if skill_id in selected_skill_ids:
                continue
            selected.append(row)
            selected_skill_ids.add(skill_id)
        return selected[:max_skill_arms]

    def matching_for_capability(self, capability: str) -> list[Mapping[str, Any]]:
        blocked = CAPABILITY_DISCOVERY_BLOCKED_SKILLS.get(capability, set())
        return [
            row
            for row in self.candidates
            if row.get("ablation_eligible") is True
            and capability in _capability_candidates(row)
            and str(row.get("skill_id") or "") not in blocked
            and self.has_capability_signal(row, capability)
        ]

    def negative_control_for_capability(self, capability: str) -> Mapping[str, Any] | None:
        quarantined = [
            row
            for row in self.candidates
            if str(row.get("safety_status") or "") == "quarantined"
            and capability not in _capability_candidates(row)
        ]
        wrong_capability = [
            row
            for row in self.candidates
            if row.get("ablation_eligible") is True
            and capability not in _capability_candidates(row)
        ]
        choices = quarantined or wrong_capability
        if not choices:
            return None
        return sorted(choices, key=lambda row: (str(row.get("sha256") or ""), str(row.get("path") or "")))[0]

    def candidate_sort_key(self, row: Mapping[str, Any], capability: str) -> tuple[int, int, int, str, str]:
        return (
            0 if row.get("runtime_eligible") is True else 1,
            self.preferred_skill_rank(row, capability),
            -self.candidate_relevance(row, capability),
            str(row.get("skill_id") or ""),
            str(row.get("path") or ""),
        )

    def preferred_skill_rank(self, row: Mapping[str, Any], capability: str) -> int:
        preferred = CAPABILITY_PREFERRED_SKILLS.get(capability, ())
        skill_id = str(row.get("skill_id") or "")
        try:
            return preferred.index(skill_id)
        except ValueError:
            return len(preferred)

    def candidate_relevance(self, row: Mapping[str, Any], capability: str) -> int:
        text = " ".join(str(row.get(key) or "") for key in ("skill_id", "load_when")).lower()
        keywords = CAPABILITY_RELEVANCE_KEYWORDS.get(capability, ())
        return sum(text.count(keyword) for keyword in keywords)

    def has_capability_signal(self, row: Mapping[str, Any], capability: str) -> bool:
        preferred = CAPABILITY_PREFERRED_SKILLS.get(capability, ())
        return self.preferred_skill_rank(row, capability) < len(preferred) or self.candidate_relevance(row, capability) > 0


def _capability_candidates(row: Mapping[str, Any]) -> set[str]:
    return {str(item) for item in row.get("capability_candidates", [])}
