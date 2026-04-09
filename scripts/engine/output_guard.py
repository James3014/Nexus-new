#!/usr/bin/env python3
"""
🛡️ Nexus Output Guard — Physical Context Shield (v23.8)

Prevents LLM context overflow by enforcing hard truncation limits
and extracting root causes from large outputs.
"""
import os
import re
import time
from pathlib import Path

# Hard limits (aligned with Goose shell.rs constants)
# Dynamic limits based on signal density (Phase 9: Semantic Guard)
LIMITS = {
    "HIGH_SIGNAL": (4000, 100_000),  # Tracebacks / Panic
    "NORMAL": (2000, 50_000),
    "LOW_SIGNAL": (500, 15_000),     # Repetitive noise
}


def _classify_output_density(text: str) -> str:
    """📊 Classify output by signal density."""
    lines = text.splitlines()
    if not lines:
        return "NORMAL"

    # 1. High Signal detection (Tracebacks / Panic)
    high_signal_patterns = [
        r"Traceback", r"Panic at", r"SEGFAULT", r"AssertionError",
        r"SUMMARY: \d+ failed",
    ]
    if any(re.search(p, text, re.I) for p in high_signal_patterns):
        return "HIGH_SIGNAL"

    # 2. Low Signal detection (Repetitive noise)
    unique_lines = len(set(lines))
    total_lines = len(lines)
    if total_lines > 100 and (unique_lines / total_lines) < 0.2:
        return "LOW_SIGNAL"

    return "NORMAL"


def truncate_output(text: str, label: str = "output") -> str:
    """
    If text exceeds limits:
    1. Writes full log to /tmp/
    2. Extracts context-rich snippets (Head + Fail Context)
    3. Returns a succinct summary for the LLM
    """
    density = _classify_output_density(text)
    limit_lines, limit_bytes = LIMITS[density]

    lines = text.splitlines()
    total_lines = len(lines)
    total_bytes = len(text.encode("utf-8"))

    if total_lines <= limit_lines and total_bytes <= limit_bytes:
        return text

    # --- Start Truncation Logic ---
    timestamp = int(time.time())
    log_file = Path(f"/tmp/nexus_{label}_{timestamp}.log")
    log_file.write_text(text, encoding="utf-8")

    # Capture the "Head" (useful for context)
    head = lines[:50]

    # Capture the "Root Cause Zone" (search from bottom for ERROR/FAIL/Exception)
    tail_sample = lines[-500:]  # Inspect last 500 lines for errors
    root_cause_lines = []

    patterns = [
        r"ERROR", r"FAILED", r"Exception", r"AssertionError",
        r"Error:", r"FAIL:",
    ]

    found_cause = False
    for i, line in enumerate(tail_sample):
        if any(re.search(p, line, re.IGNORECASE) for p in patterns):
            start = max(0, i - 5)
            end = min(len(tail_sample), i + 10)
            root_cause_lines = tail_sample[start:end]
            found_cause = True
            break

    if not found_cause:
        root_cause_lines = lines[-50:]  # Fallback to just last 50 lines

    summary = [
        f"⚠️ [OutputGuard] Output truncated ({total_lines} lines, {total_bytes} bytes).",
        f"📊 Signal Density: {density}",
        f"📁 Full log saved to: {log_file}",
        "\n--- [Head Context (First 50 lines)] ---",
        *head,
        "\n...",
        "\n--- [Root Cause Detection (Last 500 lines scan)] ---"
        if found_cause
        else "\n--- [Tail Context (Last 50 lines)] ---",
        *root_cause_lines,
        "\n...",
        f"\n💡 Hint: Use `grep -n 'ERROR\\|FAILED' {log_file}` to drill down.",
    ]

    return "\n".join(summary)


if __name__ == "__main__":
    test_text = "\n".join([f"Line {i}" for i in range(3000)])
    test_text += "\nAssertionError: failed at line 2999"
    print(truncate_output(test_text, "selftest"))
