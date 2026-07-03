from __future__ import annotations

from nexus.services.local_heal.prompt_builder import PromptBuilder


_FAKE_ORIGINAL = "Fix the normalize_score function to clamp output."
_FAKE_REPORT = "FAIL: test_clamp\nAssertionError: 1.5 not in [0,1]"
_FAKE_SEARCH = "    return (score - min_val) / (max_val - min_val)"
_FAKE_FILE = "src/utils.py"
_FAKE_STDOUT = "EVIDENCE: normalize_score does not clamp output to [0, 1] range"
_FAKE_STDERR = "Traceback: assertion failed"
_FAKE_FAILURE_KIND = "TEST_FAILURE"
_FAKE_EXIT_CODE = 1
_FAKE_CMD_HASH = "abc123"


def _build_prompt(**overrides) -> str:
    defaults = dict(
        original_user_prompt=_FAKE_ORIGINAL,
        verification_report=_FAKE_REPORT,
        canonical_search_span=_FAKE_SEARCH,
        target_file=_FAKE_FILE,
        retry_count=1,
        verifier_failure_kind=_FAKE_FAILURE_KIND,
        verifier_stdout_excerpt=_FAKE_STDOUT,
        verifier_stderr_excerpt=_FAKE_STDERR,
        verifier_exit_code=_FAKE_EXIT_CODE,
        verifier_command_hash=_FAKE_CMD_HASH,
    )
    defaults.update(overrides)
    return PromptBuilder.build_verification_guided_retry_prompt(**defaults)


def test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence():
    """RED guard: canonical locked SEARCH must appear before verifier evidence.

    Current production code places verifier_section + evidence_section BEFORE
    search_lock. This test encodes the DESIRED ordering and will FAIL until
    prompt_builder.py is patched.
    """
    prompt = _build_prompt()

    search_lock_pos = prompt.find("### CANONICAL SEARCH SPAN")
    verifier_pos = prompt.find("### VERIFICATION FAILURE REPORT")

    assert search_lock_pos >= 0, "search_lock section not found"
    assert verifier_pos >= 0, "verifier_section not found"
    assert search_lock_pos < verifier_pos, (
        f"Expected search_lock at position {search_lock_pos} to appear "
        f"BEFORE verifier_section at position {verifier_pos}. "
        f"Current ordering: verifier_section BEFORE search_lock."
    )


def test_verification_guided_retry_prompt_keeps_output_format_near_locked_search():
    """Output format instruction must follow closely after locked SEARCH."""
    prompt = _build_prompt()

    search_lock_pos = prompt.find("### CANONICAL SEARCH SPAN")
    instruction_pos = prompt.find("### INSTRUCTION")

    assert search_lock_pos >= 0, "search_lock section not found"
    assert instruction_pos >= 0, "instruction section not found"
    assert instruction_pos > search_lock_pos, (
        "instruction should follow search_lock"
    )
    gap = instruction_pos - search_lock_pos
    assert gap < 1500, (
        f"Instruction is {gap} chars after search_lock — too far apart. "
        f"Output format should be near the locked SEARCH block."
    )


def test_verification_guided_retry_prompt_preserves_verifier_evidence():
    """Verifier evidence must NOT be removed — only reordered."""
    prompt = _build_prompt()

    assert "### VERIFICATION FAILURE REPORT" in prompt, (
        "verifier_section missing from prompt"
    )
    assert _FAKE_STDOUT in prompt, "verifier_stdout_excerpt missing from prompt"
    assert "VERIFIER FAILURE EVIDENCE" in prompt, (
        "verifier evidence section missing from prompt"
    )
    assert "EVIDENCE: normalize_score" in prompt, (
        "verifier stdout evidence content missing"
    )


def test_primary_patch_system_prompt_unchanged():
    """Primary patch system prompt must remain intact (7B and non-7B)."""
    prompt_7b = PromptBuilder.build_patch_system_prompt("qwen-7b")
    assert "HARD OUTPUT CONTRACT" in prompt_7b
    assert "SEARCH" in prompt_7b
    assert "REPLACE" in prompt_7b

    prompt_large = PromptBuilder.build_patch_system_prompt("qwen-14b")
    assert "Output ONLY SEARCH/REPLACE blocks" in prompt_large
    assert "SEARCH" in prompt_large
    assert "REPLACE" in prompt_large


def test_no_route_authority_fields_change():
    """build_verification_guided_retry_prompt must not introduce route/topology."""
    import inspect

    source = inspect.getsource(PromptBuilder.build_verification_guided_retry_prompt)

    forbidden_tokens = [
        "RouteMode",
        "execution_topology",
        "CapabilityPlanner",
        "HybridRouteDecision",
    ]
    for token in forbidden_tokens:
        assert token not in source, (
            f"Forbidden route/topology token '{token}' found in "
            f"build_verification_guided_retry_prompt"
        )
