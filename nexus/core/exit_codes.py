from typing import Any, Dict, List, Optional, Tuple
"""
nexus/core/exit_codes.py
─────────────────────────────
Sprint 11 Closure #1: Four-State Terminal → CLI Exit Code Registry

This is the SINGLE SOURCE OF TRUTH for all Nexus exit code semantics.
Any system (Coordinator, CI scripts, external callers) that needs to
interpret a Nexus process's exit status MUST reference this table.

Design rules:
  - The enum values here MUST match PipelineTerminalState.value
  - Never re-use an exit code for a different semantic
  - All new terminal states require a code review + bump of EXIT_CODE_REGISTRY_VERSION
"""
from enum import IntEnum

EXIT_CODE_REGISTRY_VERSION = "v1.0"

class NexusExitCode(IntEnum):
    """
    Canonical exit code registry — four-state terminal semantics.

    ╔══════════════╦══════╦══════════════════════════════════════════════════╗
    ║ Terminal     ║ Code ║ Semantics                                        ║
    ╠══════════════╬══════╬══════════════════════════════════════════════════╣
    ║ SUCCESS      ║  0   ║ All phases passed. Evidence chain complete.       ║
    ║ FAILED       ║  1   ║ Repair failed; no human escalation needed.        ║
    ║ ESCALATED    ║  2   ║ Coordinator must re-plan; non-recoverable loop.   ║
    ║ HUMAN_REVIEW ║  3   ║ Human intervention required. Do NOT auto-retry.   ║
    ╚══════════════╩══════╩══════════════════════════════════════════════════╝

    Notes:
      - Code 0 is the ONLY code a CI gate should treat as "green".
      - Code 3 (HUMAN_REVIEW) must trigger a HandoffBundle write; external
        callers should parse this as "blocked pending operator action".
      - Codes 1-3 are all non-zero; callers MUST NOT simply check `!= 0`.
        They should compare against this registry for precise routing.
    """
    SUCCESS      = 0
    FAILED       = 1
    ESCALATED    = 2
    HUMAN_REVIEW = 3

# Human-readable descriptions for CLI output and external documentation
EXIT_CODE_DESCRIPTIONS: Dict[int, str] = {
    NexusExitCode.SUCCESS:      "✅  All phases passed. Evidence chain complete.",
    NexusExitCode.FAILED:       "❌  Repair failed within retry budget. No human escalation.",
    NexusExitCode.ESCALATED:    "⚠️  Coordinator escalation required. Re-planning needed.",
    NexusExitCode.HUMAN_REVIEW: "🧑‍💻  Human intervention required. Auto-retry is BLOCKED.",
}

# CI gate policy — which codes should fail a pipeline job
CI_BLOCKING_CODES = frozenset({
    NexusExitCode.FAILED,
    NexusExitCode.ESCALATED,
    NexusExitCode.HUMAN_REVIEW,
})

# Handoff trigger policy — which codes must generate a HandoffBundle
HANDOFF_TRIGGER_CODES = frozenset({
    NexusExitCode.HUMAN_REVIEW,
})

def describe(code: int) -> str:
    """Returns the human-readable description for a given exit code."""
    return EXIT_CODE_DESCRIPTIONS.get(code, f"Unknown exit code: {code}")

def requires_handoff(code: int) -> bool:
    """Returns True if the exit code mandates a HandoffBundle to be written."""
    return code in HANDOFF_TRIGGER_CODES

def is_ci_blocking(code: int) -> bool:
    """Returns True if this exit code should fail a CI gate."""
    return code in CI_BLOCKING_CODES
