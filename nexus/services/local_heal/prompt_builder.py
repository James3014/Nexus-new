from typing import List, Tuple, Dict, Any
from pathlib import Path

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt() -> str:
        return (
            "You are a Senior Nexus Engineer. Output surgically precise Python edits.\n\n"
            "CONTRACT:\n"
            "1. Output ONLY SEARCH/REPLACE blocks.\n"
            "2. Format: 'FILE: <path>' then '<<<<<<< SEARCH\\n<original>\\n=======\\n<fixed>\\n>>>>>>> REPLACE'.\n"
            "3. The SEARCH section must match the source code character-for-character.\n"
            "4. NO CONVERSATION. NO MARKDOWN outside blocks. NO apologies.\n"
            "5. NO PLACEHOLDERS: Never use '# ...' or comments to represent existing code."
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
            f"Produce the SEARCH/REPLACE blocks now."
        )
