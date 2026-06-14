from typing import List, Tuple, Dict, Any
from pathlib import Path
from nexus.services.local_heal.knowledge_injector import ParserHardeningKnowledgeInjector

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt(model_name: str | None = None) -> str:
        # Compact few-shot (one example, ~40 tokens)
        few_shot = (
            "\nEXAMPLE:\nFILE: src/utils.py\n"
            "<<<<<<< SEARCH\n    return os.path.join(a, b)\n=======\n"
            "    return os.path.join(a, b) if a and b else ''\n>>>>>>> REPLACE\n"
        )

        is_7b = model_name and "7b" in model_name.lower()

        if is_7b:
            return (
                "Output ONLY SEARCH/REPLACE blocks. No explanations.\n\n"
                "FILE: <path>\n<<<<<<< SEARCH\n<original>\n=======\n<fixed>\n>>>>>>> REPLACE\n\n"
                "Rules: SEARCH must match exactly. No placeholders. Write full code."
                + few_shot
            )

        return (
            "Output ONLY SEARCH/REPLACE blocks — no explanations.\n\n"
            "FILE: <path>\n<<<<<<< SEARCH\n<verbatim original>\n=======\n<fixed>\n>>>>>>> REPLACE\n\n"
            "Rules:\n"
            "1. SEARCH matches source character-for-character.\n"
            "2. No placeholders ('# ...', '... code ...'). Write complete code.\n"
            "3. Modify in-place. Use hasattr()/getattr() for dynamic access."
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
            f"{retry_section}"
            f"Allowed files: {choice_str}\n"
            f"⚠️ Rules: No placeholders. SEARCH matches source exactly. Modify in-place.\n\n"
            f"[SOURCE CONTEXT]\n{files_section}"
            f"Produce SEARCH/REPLACE blocks for: {choice_str}"
        )
