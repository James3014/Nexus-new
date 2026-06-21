"""G4: Structured Verifier Feedback Packet

Replace freeform correction prompt with structured feedback:
- failure_type
- assertion_summary
- traceback_symbol
- allowed_span
- forbidden_span
- previous_replacement
- required_output_contract

Use only one bounded correction attempt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class VerifierFeedbackPacket:
    """Structured verifier feedback for bounded correction."""
    failure_type: str  # syntax_error, assertion_error, runtime_error, import_error
    assertion_summary: str  # what the verifier expected vs got
    traceback_symbol: str  # symbol where failure occurred
    traceback_file: str  # file where failure occurred
    traceback_line: int  # line number of failure
    allowed_span: str  # what the model is allowed to change
    forbidden_span: str  # what the model must NOT change
    previous_replacement: str  # the failed replacement
    anchor_text: str  # the original anchor
    required_output_contract: str  # rules for the replacement
    raw_verifier_output: str  # full verifier output


class StructuredVerifierFeedback:
    """Parse verifier output into structured feedback packet."""

    # Common failure patterns
    SYNTAX_ERROR_RE = re.compile(r'(\w+Error):?\s*(.+?)(?:\n|$)')
    ASSERTION_ERROR_RE = re.compile(r'Assert\w*Error:\s*(.+?)(?:\n|$)')
    IMPORT_ERROR_RE = re.compile(r'ImportError:\s*(.+?)(?:\n|$)')
    NAME_ERROR_RE = re.compile(r'NameError:\s*(.+?)(?:\n|$)')
    ATTRIBUTE_ERROR_RE = re.compile(r'AttributeError:\s*(.+?)(?:\n|$)')
    TRACEBACK_FILE_RE = re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+)')
    TRACEBACK_SYMBOL_RE = re.compile(r'in\s+(\w+)')

    def parse(
        self,
        verifier_output: str,
        *,
        previous_replacement: str,
        anchor_text: str,
        allowed_span: str = "anchor body only",
        forbidden_span: str = "do not change method signature or unrelated code",
    ) -> VerifierFeedbackPacket:
        """Parse verifier output into structured feedback."""
        # Detect failure type
        failure_type = "unknown"
        assertion_summary = ""
        traceback_symbol = ""
        traceback_file = ""
        traceback_line = 0

        # Check for syntax error
        syntax_match = self.SYNTAX_ERROR_RE.search(verifier_output)
        if syntax_match:
            failure_type = "syntax_error"
            assertion_summary = f"{syntax_match.group(1)}: {syntax_match.group(2)}"

        # Check for assertion error
        assertion_match = self.ASSERTION_ERROR_RE.search(verifier_output)
        if assertion_match:
            failure_type = "assertion_error"
            assertion_summary = assertion_match.group(1)

        # Check for import error
        import_match = self.IMPORT_ERROR_RE.search(verifier_output)
        if import_match:
            failure_type = "import_error"
            assertion_summary = import_match.group(1)

        # Check for name error
        name_match = self.NAME_ERROR_RE.search(verifier_output)
        if name_match:
            failure_type = "name_error"
            assertion_summary = name_match.group(1)

        # Check for attribute error
        attr_match = self.ATTRIBUTE_ERROR_RE.search(verifier_output)
        if attr_match:
            failure_type = "attribute_error"
            assertion_summary = attr_match.group(1)

        # Extract traceback location
        file_matches = list(self.TRACEBACK_FILE_RE.finditer(verifier_output))
        if file_matches:
            last_file = file_matches[-1]
            traceback_file = last_file.group(1)
            traceback_line = int(last_file.group(2))

        # Extract traceback symbol
        symbol_matches = list(self.TRACEBACK_SYMBOL_RE.finditer(verifier_output))
        if symbol_matches:
            traceback_symbol = symbol_matches[-1].group(1)

        # Build output contract
        required_output_contract = (
            "1. Output ONLY raw Python code (no markdown, no explanation)\n"
            "2. Preserve exact indentation from the anchor\n"
            "3. Change ONLY what is needed to fix the specific failure\n"
            "4. Do not change method signatures or unrelated code\n"
            f"5. Fix the {failure_type}: {assertion_summary}"
        )

        return VerifierFeedbackPacket(
            failure_type=failure_type,
            assertion_summary=assertion_summary,
            traceback_symbol=traceback_symbol,
            traceback_file=traceback_file,
            traceback_line=traceback_line,
            allowed_span=allowed_span,
            forbidden_span=forbidden_span,
            previous_replacement=previous_replacement,
            anchor_text=anchor_text,
            required_output_contract=required_output_contract,
            raw_verifier_output=verifier_output,
        )

    def build_correction_prompt(
        self,
        packet: VerifierFeedbackPacket,
        *,
        problem: str = "",
        symbol: str = "",
    ) -> tuple[str, str]:
        """Build a correction prompt from the structured feedback packet."""
        system = (
            "You are fixing a Python bug. Your previous attempt failed verification.\n\n"
            "STRUCTURED FEEDBACK:\n"
            f"- Failure type: {packet.failure_type}\n"
            f"- Error: {packet.assertion_summary}\n"
            f"- Location: {packet.traceback_file}:{packet.traceback_line}\n"
            f"- Symbol: {packet.traceback_symbol or 'unknown'}\n\n"
            "CONSTRAINTS:\n"
            f"- Allowed span: {packet.allowed_span}\n"
            f"- Forbidden: {packet.forbidden_span}\n"
            f"- Previous failed replacement:\n{packet.previous_replacement}\n\n"
            "OUTPUT RULES:\n"
            f"{packet.required_output_contract}\n\n"
            "Output ONLY the corrected replacement code:"
        )

        user = (
            f"Bug: {problem[:300]}\n"
            f"Symbol: {symbol}\n"
            f"Original anchor:\n{packet.anchor_text}\n\n"
            f"Your failed replacement:\n{packet.previous_replacement}\n\n"
            f"Verifier error:\n{packet.raw_verifier_output[:500]}\n\n"
            "Fix the specific error and output ONLY the replacement code:"
        )

        return system, user
