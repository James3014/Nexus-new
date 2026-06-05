from typing import List, Tuple, Dict, Any
from pathlib import Path

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt(model_name: str | None = None) -> str:
        return (
            "You are a Senior Nexus Engineer. Output surgically precise Python edits.\n\n"
            "CONTRACT:\n"
            "1. Output ONLY SEARCH/REPLACE blocks.\n"
            "2. Format: 'FILE: <path>' then '<<<<<<< SEARCH\\n<original>\\n=======\\n<fixed>\\n>>>>>>> REPLACE'.\n"
            "3. The SEARCH section must match the source code character-for-character, verbatim from the provided SOURCE CONTEXT.\n"
            "4. WARNING: Code snippets in the [TASK] description may be outdated or incorrect. You MUST match the SEARCH block against the code inside [SOURCE CONTEXT], NOT the [TASK] description.\n"
            "5. NO CONVERSATION. NO MARKDOWN outside blocks. NO apologies.\n"
            "6. NO PLACEHOLDERS: Never use '# ...', '... [truncated]', '...', or comments to represent existing code. The SEARCH block must contain complete, verbatim, un-truncated original lines.\n"
            "7. NO REDEFINITION: Do not create a duplicate top-level class or function; modify the existing definition in place.\n\n"
            "SENIOR ENGINEERING RULES:\n"
            "- Python AttributeError Safety: If fixing dynamic attribute lookup (e.g. `__getattr__`), be extremely cautious about AttributeError shadowing. Under the Python descriptor protocol, properties raising AttributeError fallback to `__getattr__`. Consider delegating back to `__getattribute__` or correctly forwarding inner exceptions to prevent masking tracebacks.\n"
            "- Case-Insensitive Protocol Robustness: When parsing formats or commands that are case-insensitive by design (e.g., QDP, email headers), always ensure your regular expressions or matching logic are case-insensitive (e.g., using `re.IGNORECASE` or inline `(?i)` flag) to avoid crashes on lowercase input."
        )

    @staticmethod
    def build_patch_user_prompt(
        problem_statement: str,
        repro_evidence: str,
        plan: Dict[str, Any],
        localized_files: List[Tuple[str, str]],
        reasoning_mode: str = "INTUITIVE"
    ) -> str:
        # Context Compaction: Ensure we only show the relevant files
        files_section = ""
        for path, content in localized_files:
            files_section += f"### FILE: {path}\n{content}\n\n"

        strategy = plan.get("repair_strategy", "Apply surgical fix.")
        invariants = plan.get("violated_invariants", [])
        invariants_str = "\n".join(f"- {inv}" for inv in invariants) if invariants else "N/A"

        return (
            f"[TASK]\n{problem_statement}\n\n"
            f"[REPRODUCTION]\n{repro_evidence}\n\n"
            f"[STRATEGY: {reasoning_mode}]\n{strategy}\n"
            f"[INVARIANTS]\n{invariants_str}\n\n"
            f"[SOURCE CONTEXT]\n{files_section}"
            f"CRITICAL: Modify the existing code IN-PLACE. Do NOT duplicate or redefine existing top-level classes/functions.\n"
            f"CRITICAL: Match the SEARCH block exactly against the [SOURCE CONTEXT] files. Do NOT use the obsolete snippets from the [TASK] description.\n"
            f"Produce the SEARCH/REPLACE blocks now."
        )
