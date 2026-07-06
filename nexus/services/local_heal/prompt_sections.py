"""C6AJ: CapabilityPromptInjector — modular prompt section assembly.

Each capability implements a PromptSection that can be composed into a retry prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any


class PromptSection(Protocol):
    """Protocol for a prompt section that can be composed into a retry prompt."""
    name: str
    priority: int  # Lower = earlier in prompt

    def render(self) -> str:
        """Render the section content. Empty string = section disabled."""
        ...


@dataclass
class VerifierEvidenceSection:
    """Verifier failure evidence section."""
    name: str = "verifier_evidence"
    priority: int = 10
    failure_kind: str = ""
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    exit_code: int | str = ""
    command_hash: str = ""

    def render(self) -> str:
        if not self.failure_kind and not self.stdout_excerpt:
            return ""
        parts = []
        if self.failure_kind:
            parts.append(f"Failure kind: {self.failure_kind}")
        if self.stdout_excerpt:
            parts.append(f"Stdout:\n```\n{self.stdout_excerpt[:500]}\n```")
        if self.stderr_excerpt:
            parts.append(f"Stderr:\n```\n{self.stderr_excerpt[:500]}\n```")
        if self.exit_code:
            parts.append(f"Exit code: {self.exit_code}")
        if self.command_hash:
            parts.append(f"Command hash: {self.command_hash}")
        return "\n### VERIFIER EVIDENCE\n" + "\n".join(parts) + "\n"


@dataclass
class AssertionChecklistSection:
    """Failing assertions checklist section."""
    name: str = "assertion_checklist"
    priority: int = 15
    assertions: list[str] | None = None

    def render(self) -> str:
        if not self.assertions:
            return ""
        lines = ["\n### FAILING ASSERTIONS (your REPLACE must address ALL of these)"]
        for i, assertion in enumerate(self.assertions, 1):
            lines.append(f"{i}. {assertion}")
        lines.append("\nYour REPLACE block MUST fix ALL listed conditions above.")
        return "\n".join(lines) + "\n"


@dataclass
class MemoryLessonsSection:
    """Memory lessons from prior repairs."""
    name: str = "memory_lessons"
    priority: int = 20
    lessons: str = ""

    def render(self) -> str:
        if not self.lessons:
            return ""
        return (
            "\n### RELEVANT MEMORY LESSONS (from prior repairs)\n"
            f"{self.lessons}\n"
            "Consider these lessons when fixing the code.\n"
        )


@dataclass
class CodeIntelSection:
    """CodeIntel dependency/caller awareness context."""
    name: str = "codeintel"
    priority: int = 25
    context: str = ""

    def render(self) -> str:
        if not self.context:
            return ""
        bounded = self.context[:1500]
        return (
            "\n### CODEINTEL CONTEXT (dependency/caller awareness)\n"
            f"{bounded}\n"
            "Consider these dependencies when writing your REPLACE block.\n"
            "Do NOT modify code outside the target symbol's scope.\n"
        )


@dataclass
class ResearchPatternsSection:
    """Research repair patterns from prior successful repairs."""
    name: str = "research"
    priority: int = 30
    patterns: str = ""

    def render(self) -> str:
        if not self.patterns:
            return ""
        bounded = self.patterns[:1500]
        return (
            "\n### RESEARCH REPAIR PATTERNS (from prior successful repairs)\n"
            f"{bounded}\n"
            "Consider these proven patterns when writing your REPLACE block.\n"
        )


class CapabilityPromptInjector:
    """Composes prompt sections from multiple capabilities into a unified prompt."""

    def __init__(self):
        self._sections: list[PromptSection] = []

    def add(self, section: PromptSection) -> None:
        """Add a prompt section."""
        self._sections.append(section)

    def render_all(self) -> str:
        """Render all sections, sorted by priority."""
        sorted_sections = sorted(self._sections, key=lambda s: s.priority)
        parts = []
        for section in sorted_sections:
            rendered = section.render()
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    def section_names(self) -> list[str]:
        """Return names of all registered sections."""
        return [s.name for s in self._sections]

    def clear(self) -> None:
        """Clear all sections."""
        self._sections.clear()
