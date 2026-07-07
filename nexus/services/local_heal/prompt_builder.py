from typing import List, Tuple, Dict, Any
from pathlib import Path
from nexus.services.local_heal.knowledge_injector import ParserHardeningKnowledgeInjector
from nexus.services.local_heal.failure_memory import build_failure_context
from nexus.services.local_heal.failure_feedback_builder import build_verifier_evidence_section
from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.prompt_sections import CapabilityPromptInjector

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

        is_small_local = model_name and any(
            term in model_name.lower()
            for term in ["7b", "6.7b", "9b", "10b", "13b", "3b", "1.5b"]
        )
        
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

        if is_small_local:

            return (
                "OUTPUT: exactly one SEARCH/REPLACE block. No prose outside the block.\n\n"
                "FILE: <path>\n<<<<<<< SEARCH\n<verbatim original>\n=======\n<fixed>\n>>>>>>> REPLACE\n\n"
                "SOURCE ANCHORING (CRITICAL):\n"
                "- SEARCH must be copied EXACTLY from the CURRENT SOURCE.\n"
                "- Do NOT paraphrase, reformat, or reconstruct SEARCH from memory.\n"
                "- Do NOT change whitespace, indentation, or line breaks in SEARCH.\n"
                "- REPLACE may change logic. SEARCH may NOT change anything.\n\n"
                "FORBIDDEN:\n"
                "- Markdown code fences, unified diff format, explanations before/after blocks\n"
                "- SEARCH that differs from the provided source"
                + reasoning_section
                + few_shot
            )

        return (
            "Output ONLY SEARCH/REPLACE blocks — no explanations.\n\n"
            "SOURCE ANCHORING RULES (CRITICAL):\n"
            "- SEARCH must be copied EXACTLY from the CURRENT SOURCE / LOCKED SEARCH below.\n"
            "- Do NOT paraphrase, reformat, or reconstruct SEARCH from memory.\n"
            "- Do NOT change whitespace, indentation, or line breaks in SEARCH.\n"
            "- Do NOT include line numbers unless they are part of the source.\n"
            "- REPLACE may change logic. SEARCH may NOT change anything.\n\n"
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
            # T1.2: SEARCH_MISMATCH-specific retry guidance
            if "SEARCH_MISMATCH" in failure_reason:
                retry_section += (
                    "CRITICAL: Your SEARCH block did NOT match the source file.\n"
                    "RULES:\n"
                    "1. SEARCH MUST be an EXACT verbatim copy from the source code above.\n"
                    "2. Copy the EXACT lines including indentation — do NOT reformat.\n"
                    "3. Do NOT paraphrase, re-indent, or reconstruct from memory.\n"
                    "4. If unsure, copy a LARGER context window from the source to ensure exact match.\n"
                )
            elif "REPLACE_SYNTAX_ERROR" in failure_reason:
                retry_section += (
                    "CRITICAL: Your REPLACE block has a syntax error.\n"
                    "RULES:\n"
                    "1. Ensure indentation matches the surrounding code exactly.\n"
                    "2. Do not shift indentation levels.\n"
                    "3. Keep the same indentation as the SEARCH block you are replacing.\n"
                )
            elif "FILE_NOT_FOUND" in failure_reason:
                retry_section += (
                    "CRITICAL: The target file path was wrong.\n"
                    "RULES:\n"
                    "1. Use ONLY file paths shown in the SOURCE CONTEXT section.\n"
                    "2. Do NOT invent or guess file paths.\n"
                )
            elif "NO_EFFECTIVE_CHANGE" in failure_reason:
                retry_section += (
                    "CRITICAL: Your patch did not produce a meaningful change.\n"
                    "RULES:\n"
                    "1. The REPLACE block must differ from the SEARCH block in functional code logic.\n"
                    "2. Do not just reformat or reorder — the code behavior MUST change.\n"
                )
            elif "NO_BLOCKS_FOUND" in failure_reason:
                retry_section += (
                    "CRITICAL: Your output contained NO SEARCH/REPLACE blocks.\n"
                    "RULES:\n"
                    "1. Output ONLY SEARCH/REPLACE blocks.\n"
                    "2. Do NOT output explanations, prose, or markdown.\n"
                    "3. Use EXACTLY this format:\n"
                    "<<<<<<< SEARCH\n<verbatim original code>\n=======\n<fixed code>\n>>>>>>> REPLACE\n"
                )
            elif "REPLACEMENT_MARKDOWN_FENCE" in failure_reason:
                retry_section += (
                    "CRITICAL: Your output was wrapped in markdown code fences.\n"
                    "RULES:\n"
                    "1. Do NOT use ``` or any markdown fences.\n"
                    "2. Output the SEARCH/REPLACE blocks directly, no wrapping.\n"
                )
            elif "REPLACEMENT_PROSE_CONTAMINATION" in failure_reason:
                retry_section += (
                    "CRITICAL: Your previous output included prose or commentary instead of pure code.\n"
                    "RULES:\n"
                    "1. Output ONLY one SEARCH/REPLACE block.\n"
                    "2. Do NOT include explanations, headings, bullets, or commentary.\n"
                    "3. Do NOT describe the fix before or after the block.\n"
                    "4. The REPLACE block must contain only code.\n"
                )
            elif "UNIFIED_DIFF_OUTPUT" in failure_reason:
                retry_section += (
                    "CRITICAL: Your output used unified diff format.\n"
                    "RULES:\n"
                    "1. Do NOT use --- a/ or +++ b/ format.\n"
                    "2. Use SEARCH/REPLACE blocks only.\n"
                )
            elif "NATURAL_LANGUAGE_OUTPUT" in failure_reason:
                retry_section += (
                    "CRITICAL: Your output was natural language, not SEARCH/REPLACE blocks.\n"
                    "RULES:\n"
                    "1. Do NOT explain the fix — just output the SEARCH/REPLACE block.\n"
                    "2. Output ONLY the code change in SEARCH/REPLACE format.\n"
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

    @staticmethod
    def build_verification_guided_retry_prompt(
        original_user_prompt: str,
        verification_report: str,
        canonical_search_span: str,
        target_file: str,
        retry_count: int = 1,
        verifier_failure_kind: str = "",
        verifier_stdout_excerpt: str = "",
        verifier_stderr_excerpt: str = "",
        verifier_exit_code: int | str = "",
        verifier_command_hash: str = "",
        memory_lessons: str = "",
        codeintel_context: str = "",
        research_patterns: str = "",
        sections: CapabilityPromptInjector | None = None,
    ) -> str:
        """T1.5: Build a verification-guided retry prompt.

        Fixes the canonical SEARCH span and asks the LLM to rewrite only REPLACE
        based on verifier failure output.
        C6P: Accepts optional memory_lessons for active guidance.
        C6AJ: Accepts optional CapabilityPromptInjector for modular section assembly.
        """
        # C6AJ: If sections provided, use modular assembly
        if sections is not None:
            sections_text = sections.render_all()
            return original_user_prompt + sections_text if sections_text else original_user_prompt

        header = (
            "\n\n⚠️ [NEXUS SEMANTIC RETRY — VERIFICATION-GUIDED]\n"
            f"Retry #{retry_count}: The previous patch was applied but verification FAILED.\n"
        )

        verifier_section = (
            f"### VERIFICATION FAILURE REPORT\n"
            f"```\n{verification_report}\n```\n\n"
            f"The patch compiled and was applied, but the test still FAILS.\n"
            f"This means the REPLACE block does not address the root cause.\n\n"
        )

        # C15-3B: Inject bounded verifier evidence when available
        evidence_section = build_verifier_evidence_section(
            verifier_failure_kind=verifier_failure_kind,
            verifier_stdout_excerpt=verifier_stdout_excerpt,
            verifier_stderr_excerpt=verifier_stderr_excerpt,
            verifier_exit_code=verifier_exit_code,
            verifier_command_hash=verifier_command_hash,
        )

        # C6K: Extract and list each failing assertion as explicit checklist
        assertion_checklist = ""
        if verifier_stdout_excerpt:
            assertions = [line.strip() for line in verifier_stdout_excerpt.split("\n") if line.strip().startswith("EVIDENCE:")]
            if assertions:
                assertion_checklist = "\n### FAILING ASSERTIONS (your REPLACE must address ALL of these)\n"
                for i, assertion in enumerate(assertions, 1):
                    assertion_checklist += f"{i}. {assertion}\n"
                assertion_checklist += "\nYour REPLACE block MUST fix ALL listed conditions above.\n"

        search_lock = (
            f"### CANONICAL SEARCH SPAN (LOCKED — DO NOT MODIFY)\n"
            f"The following SEARCH block has been verified to match the source file exactly.\n"
            f"You MUST use this EXACT SEARCH block — do NOT change it.\n"
            f"Do NOT add line numbers, do NOT paraphrase, do NOT reconstruct from memory.\n"
            f"Copy the EXACT text below into your SEARCH block:\n"
            f"```\n{canonical_search_span}\n```\n\n"
        )

        instruction = (
            f"### INSTRUCTION\n"
            f"1. Keep the SEARCH block above EXACTLY as-is.\n"
            f"2. Analyze the verification failure to understand what the code actually needs.\n"
            f"3. Write ONLY a new REPLACE block that fixes the root cause.\n"
            f"4. The REPLACE block MUST address ALL failing assertions from the verifier.\n"
            f"5. Do NOT output a no-op patch (SEARCH and REPLACE must differ).\n"
            f"6. Your REPLACE must satisfy EVERY condition listed in the FAILING ASSERTIONS section.\n"
            f"7. Output format:\n"
            f"FILE: {target_file}\n"
            f"<<<<<<< SEARCH\n"
            f"<copy the canonical SEARCH span above exactly>\n"
            f"=======\n"
            f"<your fix here>\n"
            f">>>>>>> REPLACE\n\n"
            f"FORBIDDEN (will be rejected):\n"
            f"- Markdown code fences (```) around SEARCH/REPLACE\n"
            f"- Unified diff format (--- a/ or +++ b/)\n"
            f"- Explanations, prose, or text before/after blocks\n"
            f"- Missing SEARCH or REPLACE markers\n"
            f"- No-op patches where SEARCH equals REPLACE\n"
        )

        reminder = (
            "\n\nREMINDER: Output one SEARCH/REPLACE block. "
            "Keep the SEARCH block exactly as shown above. "
            "Fix only the REPLACE block.\n"
        )

        # C6P: Add memory lessons for active guidance
        memory_section = ""
        if memory_lessons:
            memory_section = (
                "\n### RELEVANT MEMORY LESSONS (from prior repairs)\n"
                f"{memory_lessons}\n"
                "Consider these lessons when fixing the code.\n"
            )

        # C6AA: Add bounded CodeIntel context for dependency awareness
        codeintel_section = ""
        if codeintel_context:
            bounded = codeintel_context[:1500]
            codeintel_section = (
                "\n### CODEINTEL CONTEXT (dependency/caller awareness)\n"
                f"{bounded}\n"
                "Consider these dependencies when writing your REPLACE block.\n"
                "Do NOT modify code outside the target symbol's scope.\n"
            )

        # C6AB: Add research repair patterns for actionable guidance
        research_section = ""
        if research_patterns:
            bounded = research_patterns[:1500]
            research_section = (
                "\n### RESEARCH REPAIR PATTERNS (from prior successful repairs)\n"
                f"{bounded}\n"
                "Consider these proven patterns when writing your REPLACE block.\n"
            )

        return original_user_prompt + header + search_lock + instruction + verifier_section + evidence_section + assertion_checklist + codeintel_section + research_section + memory_section + reminder

    @staticmethod
    def build_retry_prompt_with_injector(
        original_user_prompt: str,
        verification_report: str,
        canonical_search_span: str,
        target_file: str,
        injector: "CapabilityPromptInjector | None" = None,
        retry_count: int = 1,
    ) -> str:
        """C6AJ: Build retry prompt using CapabilityPromptInjector for modular section assembly."""
        from nexus.services.local_heal.prompt_sections import CapabilityPromptInjector

        header = (
            "\n\n⚠️ [NEXUS SEMANTIC RETRY — VERIFICATION-GUIDED]\n"
            f"Retry #{retry_count}: The previous patch was applied but verification FAILED.\n"
        )

        verifier_section = (
            f"### VERIFICATION FAILURE REPORT\n"
            f"```\n{verification_report}\n```\n\n"
            f"The patch compiled and was applied, but the test still FAILS.\n"
            f"This means the REPLACE block does not address the root cause.\n\n"
        )

        search_lock = (
            f"### CANONICAL SEARCH SPAN (LOCKED — DO NOT MODIFY)\n"
            f"The following SEARCH block has been verified to match the source file exactly.\n"
            f"You MUST use this EXACT SEARCH block — do NOT change it.\n"
            f"Do NOT add line numbers, do NOT paraphrase, do NOT reconstruct from memory.\n"
            f"Copy the EXACT text below into your SEARCH block:\n"
            f"```\n{canonical_search_span}\n```\n\n"
        )

        instruction = (
            f"### INSTRUCTION\n"
            f"1. Keep the SEARCH block above EXACTLY as-is.\n"
            f"2. Analyze the verification failure to understand what the code actually needs.\n"
            f"3. Write ONLY a new REPLACE block that fixes the root cause.\n"
            f"4. The REPLACE block MUST address ALL failing assertions from the verifier.\n"
            f"5. Do NOT output a no-op patch (SEARCH and REPLACE must differ).\n"
            f"6. Your REPLACE must satisfy EVERY condition listed in the FAILING ASSERTIONS section.\n"
            f"7. Output format:\n"
            f"FILE: {target_file}\n"
            f"<<<<<<< SEARCH\n"
            f"<copy the canonical SEARCH span above exactly>\n"
            f"=======\n"
            f"<your fix here>\n"
            f">>>>>>> REPLACE\n\n"
            f"FORBIDDEN (will be rejected):\n"
            f"- Markdown code fences (```) around SEARCH/REPLACE\n"
            f"- Unified diff format (--- a/ or +++ b/)\n"
            f"- Explanations, prose, or text before/after blocks\n"
            f"- Missing SEARCH or REPLACE markers\n"
            f"- No-op patches where SEARCH equals REPLACE\n"
        )

        reminder = (
            "\n\nREMINDER: Output one SEARCH/REPLACE block. "
            "Keep the SEARCH block exactly as shown above. "
            "Fix only the REPLACE block.\n"
        )

        # Render injector sections
        injector_sections = ""
        if injector:
            injector_sections = injector.render_all()

        return original_user_prompt + header + search_lock + instruction + verifier_section + injector_sections + reminder
