from typing import List, Tuple, Dict, Any
from pathlib import Path
from nexus.services.local_heal.knowledge_injector import ParserHardeningKnowledgeInjector
from nexus.services.local_heal.failure_memory import build_failure_context
from nexus.services.local_heal.interface import LocalizedFile

class PromptBuilder:
    """🛡️ Nexus Prompt Engineering & Contract Management (Linus Principles: Explicit & Reliable)"""

    @staticmethod
    def build_patch_system_prompt(model_name: str | None = None, interleaved: bool = False) -> str:
        # Compact few-shot (one example, ~40 tokens)
        few_shot = (
            "\nEXAMPLE:\nFILE: src/utils.py\n"
            "<<<<<<< SEARCH\n    return os.path.join(a, b)\n=======\n"
            "    return os.path.join(a, b) if a and b else ''\n>>>>>>> REPLACE\n"
        )

        is_7b = model_name and "7b" in model_name.lower()
        
        # Interleaved mode: add reasoning section for planning + patch in one call
        reasoning_section = ""
        if interleaved:
            reasoning_section = (
                "\nBefore producing the patch, briefly analyze:\n"
                "1. Which symbols/functions are involved\n"
                "2. What the root cause is\n"
                "3. The minimal fix needed\n"
                "Then produce the SEARCH/REPLACE patch.\n"
            )

        if is_7b:
            return (
                "Output ONLY SEARCH/REPLACE blocks. No explanations.\n\n"
                "FILE: <path>\n<<<<<<< SEARCH\n<original>\n=======\n<fixed>\n>>>>>>> REPLACE\n\n"
                "Rules: SEARCH must match exactly. No placeholders. Write full code."
                + reasoning_section
                + few_shot
            )

        return (
            "Output ONLY SEARCH/REPLACE blocks — no explanations.\n\n"
            "FILE: <path>\n<<<<<<< SEARCH\n<verbatim original>\n=======\n<fixed>\n>>>>>>> REPLACE\n\n"
            "Rules:\n"
            "1. SEARCH matches source character-for-character.\n"
            "2. No placeholders ('# ...', '... code ...'). Write complete code.\n"
            "3. Modify in-place. Use hasattr()/getattr() for dynamic access.\n"
            "4. Indentation: The indentation of the code inside the REPLACE block must match the surrounding indentation exactly. Do not shift indentation levels."
            + reasoning_section
            + few_shot
        )

    @staticmethod
    def build_patch_user_prompt(
        problem_statement: str,
        repro_evidence: str,
        plan: Any,
        localized_files: List[LocalizedFile],
        reasoning_mode: str = "INTUITIVE",
        failure_reason: str = "",
        attempt: int = 1,
        project_root: Path | None = None,
        max_prompt_tokens: int = 6000,
        repair_specification: str = "",
    ) -> str:
        # 1. 自動偵測並注入領域知識 (Knowledge Slicing)
        hardening_context = ""
        for loc_file in localized_files:
            profile = ParserHardeningKnowledgeInjector.detect_profile(problem_statement, loc_file.content)
            if profile:
                hardening_context += ParserHardeningKnowledgeInjector.get_profile_prompt(profile)

        strategy = getattr(plan, "repair_strategy", "Apply surgical fix.")
        
        # 2. Repair Specification (P0 Priority: Logic intent)
        spec_section = ""
        if repair_specification:
            spec_section = f"\n[REPAIR SPECIFICATION (MANDATORY)]\n{repair_specification}\n"

        # 3. Retry failure context injection
        retry_section = ""
        if attempt > 1 and failure_reason:
            retry_section = (
                f"\n⚠️ [RETRY CONTEXT] Previous attempt #{attempt-1} FAILED: {failure_reason}\n"
                f"DO NOT repeat the same mistake. Analyze why it failed and produce a DIFFERENT fix.\n"
            )

        # 3. Failure memory bank
        failure_memory_section = ""
        if project_root:
            failure_context = build_failure_context(project_root)
            if failure_context:
                failure_memory_section = f"\n{failure_context}\n"

        # 5. Context Budgeting & Compaction
        # Estimate fixed parts (~3 chars per token heuristic)
        base_prompt = (
            f"{hardening_context}\n"
            f"[TASK]\n{problem_statement}\n\n"
            f"[REPRODUCTION]\n{repro_evidence}\n\n"
            f"{spec_section}"
            f"[STRATEGY: {reasoning_mode}]\n{strategy}\n"
            f"{retry_section}"
            f"{failure_memory_section}"
            f"⚠️ Rules: No placeholders. SEARCH matches source exactly. Modify in-place.\n\n"
        )
        
        base_tokens = len(base_prompt) // 3
        available_tokens = max_prompt_tokens - base_tokens
        
        files_section = ""
        choice_set = []
        
        # Simple token budgeting for files
        current_files_tokens = 0
        for loc_file in localized_files:
            path, content = loc_file.path, loc_file.content
            choice_set.append(path)
            file_header = f"### FILE: {path}\n"
            file_footer = "\n\n"
            
            # If single file is huge, truncate it
            file_tokens = (len(file_header) + len(content) + len(file_footer)) // 3
            
            if current_files_tokens + file_tokens > available_tokens:
                # Truncate content to fit remaining budget
                remaining_chars = (available_tokens - current_files_tokens) * 3
                if remaining_chars > 500:
                    truncated_content = content[:remaining_chars] + "\n... [TRUNCATED DUE TO CONTEXT LIMIT] ..."
                    files_section += f"{file_header}{truncated_content}{file_footer}"
                else:
                    files_section += f"### FILE: {path}\n... [SKIPPED DUE TO CONTEXT LIMIT] ...\n\n"
                break
            else:
                files_section += f"{file_header}{content}{file_footer}"
                current_files_tokens += file_tokens

        choice_str = ", ".join(choice_set)
        
        return (
            f"{base_prompt}"
            f"Allowed files: {choice_str}\n"
            f"[SOURCE CONTEXT]\n{files_section}"
            f"Produce SEARCH/REPLACE blocks for: {choice_str}"
        )
