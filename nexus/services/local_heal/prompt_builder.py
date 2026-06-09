from typing import List, Tuple, Dict, Any
from pathlib import Path
from nexus.services.local_heal.knowledge_injector import ParserHardeningKnowledgeInjector

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt(model_name: str | None = None) -> str:
        return (
            "You are a Senior Nexus Engineer. Output surgically precise Python edits.\n\n"
            "CONTRACT (SolidSearchReplace v1):\n"
            "1. Output ONLY SEARCH/REPLACE blocks.\n"
            "2. Format: 'FILE: <path>' then '<<<<<<< SEARCH\\n<original>\\n=======\\n<fixed>\\n>>>>>>> REPLACE'.\n"
            "3. The SEARCH section must match the source code character-for-character, verbatim from the provided SOURCE CONTEXT.\n"
            "4. NO CONVERSATION. NO apologies. Output ONLY the code blocks.\n"
            "5. NO PLACEHOLDERS: Never use '# ...', '... [truncated]', or comments to represent existing code. The SEARCH block must contain complete, verbatim, un-truncated original lines.\n"
            "6. NO REDEFINITION: Do not create a duplicate top-level class or function; modify the existing definition in place.\n"
            "\nSENIOR ENGINEERING RULES:\n"
            "- AttributeError Safety: Always use hasattr() or getattr() with defaults before accessing dynamic attributes.\n"
            "- Case-Insensitive Protocol: String comparisons against user input must use .lower() or .casefold().\n"
            "- Fail loudly: Raise explicit exceptions with context instead of returning None silently.\n"
        )

    @staticmethod
    def build_patch_user_prompt(
        problem_statement: str,
        repro_evidence: str,
        plan: Dict[str, Any],
        localized_files: List[Tuple[str, str]],
        reasoning_mode: str = "INTUITIVE"
    ) -> str:
        # 1. 自動偵測並注入領域知識 (Knowledge Slicing)
        hardening_context = ""
        for _, content in localized_files:
            profile = ParserHardeningKnowledgeInjector.detect_profile(problem_statement, content)
            if profile:
                hardening_context += ParserHardeningKnowledgeInjector.get_profile_prompt(profile)

        # 2. Context Compaction
        files_section = ""
        for path, content in localized_files:
            files_section += f"### FILE: {path}\n{content}\n\n"

        strategy = plan.get("repair_strategy", "Apply surgical fix.")
        invariants = plan.get("violated_invariants", [])
        invariants_str = "\n".join(f"- {inv}" for inv in invariants) if invariants else "N/A"

        return (
            f"{hardening_context}\n"
            f"[TASK]\n{problem_statement}\n\n"
            f"[REPRODUCTION]\n{repro_evidence}\n\n"
            f"[STRATEGY: {reasoning_mode}]\n{strategy}\n"
            f"[INVARIANTS]\n{invariants_str}\n\n"
            f"⚠️ VERBATIM RULE: The code below is extracted CHARACTER-FOR-CHARACTER from the actual source files.\n"
            f"Your SEARCH block MUST be copied exactly from here. Do NOT rewrite, paraphrase, or invent code.\n"
            f"Line numbers (e.g. '  42 | ') are for reference ONLY — exclude them from your SEARCH block.\n\n"
            f"[SOURCE CONTEXT]\n{files_section}"
            f"CRITICAL: Modify the existing code IN-PLACE using the SEARCH/REPLACE protocol.\n"
            f"CRITICAL: Match the SEARCH block EXACTLY against the [SOURCE CONTEXT].\n"
            f"Produce the SEARCH/REPLACE blocks now."
        )
