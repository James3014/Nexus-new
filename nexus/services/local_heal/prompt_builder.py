from typing import List, Tuple, Dict, Any
from pathlib import Path
from nexus.services.local_heal.knowledge_injector import ParserHardeningKnowledgeInjector

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt(model_name: str | None = None) -> str:
        # P0-4: Few-shot example drastically improves 7B format compliance
        few_shot = (
            "\n\nEXAMPLE 1 (follow this exact format):\n"
            "FILE: django/db/models/query.py\n"
            "<<<<<<< SEARCH\n"
            "        if self.query.is_empty():\n"
            "            return False\n"
            "=======\n"
            "        if self.query.is_empty():\n"
            "            return self.query.default_cols\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "EXAMPLE 2:\n"
            "FILE: astropy/coordinates/angles.py\n"
            "<<<<<<< SEARCH\n"
            "    def __str__(self):\n"
            "        return self.to_string()\n"
            "=======\n"
            "    def __str__(self):\n"
            "        try:\n"
            "            return self.to_string()\n"
            "        except Exception:\n"
            "            return super().__str__()\n"
            ">>>>>>> REPLACE\n"
        )

        is_7b = False
        if model_name and "7b" in model_name.lower():
            is_7b = True

        if is_7b:
            # Slim prompt (< 150 tokens) for 7B models
            return (
                "You are a Senior Python Developer. Output ONLY SEARCH/REPLACE blocks (no explanations).\n\n"
                "Format:\n"
                "FILE: <path>\n"
                "<<<<<<< SEARCH\n"
                "<exact original code>\n"
                "=======\n"
                "<fixed code>\n"
                ">>>>>>> REPLACE\n"
                "Rules:\n"
                "1. SEARCH must match source exactly character-for-character.\n"
                "2. NO placeholders (e.g. '# ...') in SEARCH or REPLACE block. You must write full code.\n"
                "3. Modify existing code in-place.\n"
                + few_shot
            )

        return (
            "You are a Senior Software Engineer fixing a Python bug.\n"
            "OUTPUT ONLY SEARCH/REPLACE blocks — no explanations, no apologies.\n\n"
            "FORMAT:\n"
            "FILE: <path/to/file.py>\n"
            "<<<<<<< SEARCH\n"
            "<exact original code, verbatim>\n"
            "=======\n"
            "<fixed code>\n"
            ">>>>>>> REPLACE\n\n"
            "RULES:\n"
            "1. SEARCH must match source CHARACTER-FOR-CHARACTER.\n"
            "2. NO placeholders (e.g. '# ...', '// ...', '... existing code ...') in SEARCH or REPLACE blocks. You must write out the complete code.\n"
            "3. Do NOT redefine top-level classes/functions — modify in-place.\n"
            "4. Use hasattr()/getattr() before dynamic attribute access.\n"
            + few_shot
        )

    @staticmethod
    def build_patch_user_prompt(
        problem_statement: str,
        repro_evidence: str,
        plan: Dict[str, Any],
        localized_files: List[Tuple[str, str]],
        reasoning_mode: str = "INTUITIVE",
        failure_reason: str = "",
        attempt: int = 1,
    ) -> str:
        # 1. 自動偵測並注入領域知識 (Knowledge Slicing)
        hardening_context = ""
        for _, content in localized_files:
            profile = ParserHardeningKnowledgeInjector.detect_profile(problem_statement, content)
            if profile:
                hardening_context += ParserHardeningKnowledgeInjector.get_profile_prompt(profile)

        # 2. Context Compaction
        files_section = ""
        choice_set = []
        for path, content in localized_files:
            files_section += f"### FILE: {path}\n{content}\n\n"
            choice_set.append(path)

        choice_str = ", ".join(choice_set)

        strategy = plan.get("repair_strategy", "Apply surgical fix.")
        invariants = plan.get("violated_invariants", [])
        invariants_str = "\n".join(f"- {inv}" for inv in invariants) if invariants else "N/A"

        # 3. Retry failure context injection
        retry_section = ""
        if attempt > 1 and failure_reason:
            retry_section = (
                f"\n⚠️ [RETRY CONTEXT] Previous attempt #{attempt-1} FAILED: {failure_reason}\n"
                f"DO NOT repeat the same mistake. Analyze why it failed and produce a DIFFERENT fix.\n"
            )

        return (
            f"{hardening_context}\n"
            f"[TASK]\n{problem_statement}\n\n"
            f"[REPRODUCTION]\n{repro_evidence}\n\n"
            f"[STRATEGY: {reasoning_mode}]\n{strategy}\n"
            f"[INVARIANTS]\n{invariants_str}\n\n"
            f"{retry_section}"
            f"⚠️ CRITICAL: NO placeholders (e.g., '# ...', '... existing code ...') are allowed. You MUST write out the complete, actual code inside REPLACE block.\n"
            f"⚠️ CRITICAL: You MUST only modify files listed in the [SOURCE CONTEXT] below.\n"
            f"Allowed files: {choice_str}\n\n"
            f"⚠️ VERBATIM RULE: The code below is extracted CHARACTER-FOR-CHARACTER from the actual source files.\n"
            f"Your SEARCH block MUST be copied exactly from here. Do NOT rewrite, paraphrase, or invent code.\n"
            f"Line numbers (e.g. '  42 | ') are for reference ONLY — exclude them from your SEARCH block.\n\n"
            f"[SOURCE CONTEXT]\n{files_section}"
            f"CRITICAL: Modify the existing code IN-PLACE using the SEARCH/REPLACE protocol.\n"
            f"CRITICAL: Match the SEARCH block EXACTLY against the [SOURCE CONTEXT].\n"
            f"Produce the SEARCH/REPLACE blocks now for the files: {choice_str}"
        )
