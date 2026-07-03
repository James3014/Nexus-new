from __future__ import annotations

import hashlib
import re

def build_failure_feedback(
    task_id: str,
    failure_class: str,
    target_file: str,
    target_symbol: str,
    locked_search: str,
    previous_block_reason: str,
    verifier_status: str,
    stdout_tail: str = "",
    stderr_tail: str = "",
) -> str:
    """Build abbreviated feedback prompt for failure-guided retry."""
    
    # 抽取 minimal stdout/stderr 尾部日誌 (避免噪音與過長 token)
    clean_stdout = _prune_log_tail(stdout_tail)
    clean_stderr = _prune_log_tail(stderr_tail)
    
    log_section = ""
    if clean_stderr:
        log_section += f"Stderr tail:\n```\n{clean_stderr}\n```\n"
    elif clean_stdout:
        log_section += f"Stdout tail:\n```\n{clean_stdout}\n```\n"
        
    if failure_class == "REPLACEMENT_MARKDOWN_FENCE":
        feedback = (
            f"Your previous output was rejected because it contained markdown fences.\n"
            f"Task ID: {task_id}\n"
            f"Failure Class: {failure_class}\n"
            f"Previous Block Reason: {previous_block_reason}\n\n"
            f"CRITICAL OUTPUT RULES:\n"
            f"- Do NOT use markdown fences (```).\n"
            f"- Do NOT output ```python or ```diff.\n"
            f"- Output ONLY the replacement code inside the required REPLACE block.\n"
            f"- No prose, no explanation, no commentary.\n\n"
            f"Target File: {target_file}\n"
            f"Target Symbol: {target_symbol}\n"
            f"Locked Search Span (you MUST only modify code within this block):\n"
            f"```\n{locked_search}\n```\n\n"
            f"Output format:\n"
            f"<<<<<<< REPLACE\n"
            f"[your replacement code here]\n"
            f">>>>>>> REPLACE\n"
        )
        return feedback

    if failure_class == "REPLACEMENT_PROSE_CONTAMINATION":
        feedback = (
            f"Your previous output was rejected because it contained prose or commentary instead of pure replacement code.\n"
            f"Task ID: {task_id}\n"
            f"Failure Class: {failure_class}\n"
            f"Previous Block Reason: {previous_block_reason}\n\n"
            f"CRITICAL OUTPUT RULES:\n"
            f"- Output ONLY replacement code.\n"
            f"- Do NOT include explanations, bullet points, headings, or commentary.\n"
            f"- Do NOT include markdown fences (```).\n"
            f"- Output ONLY the replacement code inside the required REPLACE block.\n\n"
            f"Target File: {target_file}\n"
            f"Target Symbol: {target_symbol}\n"
            f"Locked Search Span (you MUST only modify code within this block):\n"
            f"```\n{locked_search}\n```\n\n"
            f"Output format:\n"
            f"<<<<<<< REPLACE\n"
            f"[your replacement code here]\n"
            f">>>>>>> REPLACE\n"
        )
        return feedback

    feedback = (
        f"Your previous unified diff failed verification.\n"
        f"Task ID: {task_id}\n"
        f"Failure Class: {failure_class}\n"
        f"Previous Block Reason: {previous_block_reason}\n"
        f"Verifier Status: {verifier_status}\n\n"
        f"{log_section}"
        f"Target File: {target_file}\n"
        f"Target Symbol: {target_symbol}\n"
        f"Locked Search Span (you MUST only modify code within this block):\n"
        f"```\n{locked_search}\n```\n\n"
        f"Please analyze the failure, correct your code, and generate a new unified diff.\n"
        f"Output Contract: Return ONLY a valid unified diff wrapped in ```diff block. No prose or explanations."
    )
    return feedback

def _prune_log_tail(log: str, max_lines: int = 15) -> str:
    """Prune logs to retain only the last few lines to avoid token explosion."""
    if not log:
        return ""
    lines = log.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines).strip()


def build_verifier_evidence_section(
    verifier_failure_kind: str,
    verifier_stdout_excerpt: str,
    verifier_stderr_excerpt: str,
    verifier_exit_code: int | str,
    verifier_command_hash: str,
) -> str:
    """Build bounded verifier evidence section for semantic retry prompt.
    
    Must not include raw verifier command, unbounded stdout/stderr,
    any route decision, any instruction to bypass verifier,
    or any instruction to mark solved.
    """
    if not verifier_failure_kind:
        return ""

    section = "\n### VERIFIER FAILURE EVIDENCE (bounded, for root-cause analysis only)\n"
    section += f"- Failure kind: {verifier_failure_kind}\n"
    if verifier_exit_code != "" and verifier_exit_code is not None:
        section += f"- Exit code: {verifier_exit_code}\n"
    if verifier_command_hash:
        section += f"- Command hash: {verifier_command_hash}\n"
    if verifier_stdout_excerpt:
        section += f"- Stdout excerpt (bounded):\n```\n{verifier_stdout_excerpt[:1000]}\n```\n"
    if verifier_stderr_excerpt:
        section += f"- Stderr excerpt (bounded):\n```\n{verifier_stderr_excerpt[:1000]}\n```\n"
    section += (
        "\nANALYZE the failure evidence above to understand what went wrong.\n"
        "The verifier remains final authority — your new patch must still pass verification.\n"
        "Output must remain SEARCH/REPLACE protocol. No prose, no markdown fences.\n"
    )
    return section


def compute_verifier_evidence_hash(
    verifier_failure_kind: str,
    verifier_stdout_excerpt: str,
    verifier_stderr_excerpt: str,
    verifier_exit_code: int | str,
    verifier_command_hash: str,
) -> str:
    """Compute a deterministic hash of the verifier evidence for receipt tracking."""
    parts = [
        verifier_failure_kind,
        str(verifier_exit_code),
        verifier_command_hash,
        verifier_stdout_excerpt[:200],
        verifier_stderr_excerpt[:200],
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
