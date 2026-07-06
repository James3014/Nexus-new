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


@dataclass
class XRaySection:
    """XRayObserver findings section for dependency awareness."""
    name: str = "xray"
    priority: int = 22
    symbols: list[str] | None = None
    crossings: list[dict[str, str]] | None = None
    risks: list[str] | None = None

    def render(self) -> str:
        if not self.symbols and not self.crossings and not self.risks:
            return ""
        parts = ["\n### XRAY DEPENDENCY ANALYSIS"]
        if self.symbols:
            parts.append(f"Symbols found: {', '.join(self.symbols[:10])}")
        if self.crossings:
            high_coupling = [c for c in self.crossings if c.get("source", "").endswith(".py")]
            if high_coupling:
                pairs = [f"{c.get('source', '?')} → {c.get('target', '?')}" for c in high_coupling[:5]]
                parts.append(f"Key crossings: {'; '.join(pairs)}")
        if self.risks:
            parts.append("Risks:")
            for risk in self.risks[:3]:
                parts.append(f"  - {risk}")
        parts.append("Consider these dependencies when writing your REPLACE block.\n")
        return "\n".join(parts) + "\n"


@dataclass
class SandboxSection:
    """SandboxRunner isolated execution results section."""
    name: str = "sandbox"
    priority: int = 35
    sandbox_passed: bool = False
    sandbox_output: str = ""
    sandbox_error: str = ""

    def render(self) -> str:
        if not self.sandbox_output and not self.sandbox_error:
            return ""
        parts = ["\n### SANDBOX EXECUTION RESULT"]
        parts.append(f"Status: {'PASSED' if self.sandbox_passed else 'FAILED'}")
        if self.sandbox_output:
            parts.append(f"Output:\n```\n{self.sandbox_output[:500]}\n```")
        if self.sandbox_error:
            parts.append(f"Error:\n```\n{self.sandbox_error[:500]}\n```")
        parts.append("Use this feedback to improve your REPLACE block.\n")
        return "\n".join(parts) + "\n"
