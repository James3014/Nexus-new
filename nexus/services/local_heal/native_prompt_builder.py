"""B1-C: Prompt Builder Rewire — Build prompts from native evidence packets."""
from __future__ import annotations

from nexus.services.local_heal.native_evidence_packet import EvidencePacket


class NativePromptBuilder:
    """Builds model prompts from native evidence packets."""

    def build_prompt(
        self,
        *,
        evidence_packet: EvidencePacket,
        problem_statement: str,
        anchor_text: str,
        retry_feedback: str = "",
    ) -> str:
        """Build a model prompt from the native evidence packet."""
        sections = []

        # Task summary
        sections.append(f"[TASK]\n{problem_statement}")

        # Issue intent
        sections.append(f"[ISSUE INTENT]\n{evidence_packet.issue_intent}")

        # Selected anchor
        anchor = evidence_packet.selected_anchor
        sections.append(
            f"[SELECTED ANCHOR]\n"
            f"Symbol: {anchor['symbol']}\n"
            f"File: {anchor['file']}\n"
            f"Span: L{anchor['start_line']}-L{anchor['end_line']}\n"
            f"Preview:\n{anchor['source_text_preview']}"
        )

        # Allowed edit span
        sections.append(
            f"[ALLOWED EDIT SPAN]\n"
            f"Replace only the selected anchor. Do not modify other methods or files."
        )

        # Bounded CodeIntel evidence
        if evidence_packet.codeintel_evidence:
            codeintel_section = "[CODEINTEL EVIDENCE]\n"
            for item in evidence_packet.codeintel_evidence[:5]:
                codeintel_section += (
                    f"- {item.symbol} ({item.relation}): {item.relevance_reason}\n"
                    f"  File: {item.file}, Lines: {item.start_line}-{item.end_line}\n"
                )
            sections.append(codeintel_section)

        # Bounded memory evidence
        if evidence_packet.memory_evidence:
            memory_section = "[PRIOR LESSONS]\n"
            for item in evidence_packet.memory_evidence[:3]:
                memory_section += f"- {item.summary} (source: {item.provenance})\n"
            sections.append(memory_section)

        # Missing context risks
        if evidence_packet.missing_context_risks:
            risks = ", ".join(evidence_packet.missing_context_risks)
            sections.append(f"[CONTEXT RISKS]\n{risks}")

        # Retry feedback
        if retry_feedback:
            sections.append(f"[RETRY FEEDBACK]\n{retry_feedback}")

        # Strict output contract
        sections.append(
            "[OUTPUT CONTRACT]\n"
            "1. Output ONLY raw Python code (max 12 lines)\n"
            "2. NEVER wrap in ```python ... ``` fences\n"
            "3. NEVER add explanation\n"
            "4. Preserve exact indentation from the anchor\n"
            "5. Change ONLY what fixes the bug\n"
            "6. If uncertain, output: ABSTAIN"
        )

        # Code to replace
        sections.append(f"[CODE TO REPLACE]\n{anchor_text}")

        return "\n\n".join(sections)
