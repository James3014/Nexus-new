"""C6AJ: CapabilityPromptInjector tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.prompt_sections import (
    CapabilityPromptInjector,
    VerifierEvidenceSection,
    AssertionChecklistSection,
    MemoryLessonsSection,
    CodeIntelSection,
    ResearchPatternsSection,
)


def test_prompt_section_protocol():
    """PromptSection protocol must be implementable."""
    section = VerifierEvidenceSection()
    assert hasattr(section, "name")
    assert hasattr(section, "priority")
    assert hasattr(section, "render")


def test_verifier_evidence_section_render():
    """VerifierEvidenceSection renders when failure_kind is set."""
    section = VerifierEvidenceSection(failure_kind="assertion_mismatch")
    rendered = section.render()
    assert "VERIFIER EVIDENCE" in rendered
    assert "assertion_mismatch" in rendered


def test_verifier_evidence_section_empty():
    """VerifierEvidenceSection renders empty when no data."""
    section = VerifierEvidenceSection()
    assert section.render() == ""


def test_assertion_checklist_section_render():
    """AssertionChecklistSection renders with assertions."""
    section = AssertionChecklistSection(assertions=["assert x > 0", "assert y != 0"])
    rendered = section.render()
    assert "FAILING ASSERTIONS" in rendered
    assert "assert x > 0" in rendered
    assert "assert y != 0" in rendered


def test_assertion_checklist_section_empty():
    """AssertionChecklistSection renders empty when no assertions."""
    section = AssertionChecklistSection()
    assert section.render() == ""


def test_memory_lessons_section_render():
    """MemoryLessonsSection renders with lessons."""
    section = MemoryLessonsSection(lessons="Use clamping for division")
    rendered = section.render()
    assert "MEMORY LESSONS" in rendered
    assert "clamping" in rendered


def test_memory_lessons_section_empty():
    """MemoryLessonsSection renders empty when no lessons."""
    section = MemoryLessonsSection()
    assert section.render() == ""


def test_codeintel_section_render():
    """CodeIntelSection renders with context."""
    section = CodeIntelSection(context="func_a callers: func_b, func_c")
    rendered = section.render()
    assert "CODEINTEL CONTEXT" in rendered
    assert "func_a callers" in rendered


def test_codeintel_section_empty():
    """CodeIntelSection renders empty when no context."""
    section = CodeIntelSection()
    assert section.render() == ""


def test_research_patterns_section_render():
    """ResearchPatternsSection renders with patterns."""
    section = ResearchPatternsSection(patterns="Pattern 1: Use guard clause")
    rendered = section.render()
    assert "RESEARCH REPAIR PATTERNS" in rendered
    assert "guard clause" in rendered


def test_research_patterns_section_empty():
    """ResearchPatternsSection renders empty when no patterns."""
    section = ResearchPatternsSection()
    assert section.render() == ""


def test_capability_prompt_injector_add_and_render():
    """CapabilityPromptInjector composes sections by priority."""
    injector = CapabilityPromptInjector()
    injector.add(MemoryLessonsSection(lessons="lesson 1"))
    injector.add(CodeIntelSection(context="context 1"))
    injector.add(VerifierEvidenceSection(failure_kind="test_fail"))

    rendered = injector.render_all()
    assert "VERIFIER EVIDENCE" in rendered
    assert "CODEINTEL CONTEXT" in rendered
    assert "MEMORY LESSONS" in rendered

    # Priority order: verifier (10) < codeintel (25) < memory (20)
    # Actually: verifier (10) < memory (20) < codeintel (25)
    pos_verifier = rendered.index("VERIFIER EVIDENCE")
    pos_memory = rendered.index("MEMORY LESSONS")
    pos_codeintel = rendered.index("CODEINTEL CONTEXT")
    assert pos_verifier < pos_memory < pos_codeintel


def test_capability_prompt_injector_empty_sections():
    """CapabilityPromptInjector returns empty when all sections empty."""
    injector = CapabilityPromptInjector()
    injector.add(VerifierEvidenceSection())
    injector.add(CodeIntelSection())
    assert injector.render_all() == ""


def test_capability_prompt_injector_section_names():
    """CapabilityPromptInjector tracks section names."""
    injector = CapabilityPromptInjector()
    injector.add(MemoryLessonsSection())
    injector.add(CodeIntelSection())
    assert injector.section_names() == ["memory_lessons", "codeintel"]


def test_capability_prompt_injector_clear():
    """CapabilityPromptInjector.clear removes all sections."""
    injector = CapabilityPromptInjector()
    injector.add(MemoryLessonsSection(lessons="test"))
    assert len(injector.render_all()) > 0
    injector.clear()
    assert injector.render_all() == ""
    assert injector.section_names() == []


def test_prompt_builder_accepts_sections():
    """PromptBuilder.build_verification_guided_retry_prompt accepts sections param."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    injector = CapabilityPromptInjector()
    injector.add(VerifierEvidenceSection(failure_kind="test"))

    result = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix the bug",
        verification_report="FAIL",
        canonical_search_span="def func():",
        target_file="app.py",
        sections=injector,
    )
    assert "VERIFIER EVIDENCE" in result
    assert "test" in result
