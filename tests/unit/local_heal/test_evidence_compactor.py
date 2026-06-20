import pytest
from nexus.services.local_heal.evidence_compactor import (
    EvidenceCompactor,
    StructuredPacket,
)


SAMPLE_TRACEBACK = """\
Running tests...
test foo.py::test_bar PASSED
test foo.py::test_baz FAILED

========================= FAILURES ==========================
___ test_baz ___

    def test_baz():
>       assert 1 == 2
E       assert 1 == 2

tests/test_foo.py:42: AssertionError

========================= 1 failed in 5.00s =========================
"""

LARGE_TRACEBACK = "line of output\n" * 5000 + "AssertionError: mismatch\n"


def test_structured_packet_to_prompt_text():
    packet = StructuredPacket(
        exception_type="AssertionError",
        exception_message="assert 1 == 2",
        top_failing_file="tests/test_foo.py",
        top_failing_line=42,
        repro_command="pytest tests/test_foo.py::test_baz",
        relevant_source_span="    def test_baz():\n>       assert 1 == 2",
        env_failure_reason="",
        omitted_bytes=0,
        raw_artifact_ref="artifacts/test_baz.json",
    )
    text = packet.to_prompt_text()
    assert "[EXCEPTION] AssertionError: assert 1 == 2" in text
    assert "[LOCATION] tests/test_foo.py:42" in text
    assert "[REPRO] pytest tests/test_foo.py::test_baz" in text
    assert "[SOURCE]" in text
    assert "[RAW_REF] artifacts/test_baz.json" in text


def test_structured_packet_to_prompt_text_truncation():
    packet = StructuredPacket(
        exception_type="Error",
        exception_message="x" * 500,
        top_failing_file="a.py",
        top_failing_line=1,
        repro_command="",
        relevant_source_span="x" * 3000,
        env_failure_reason="",
        omitted_bytes=1000,
        raw_artifact_ref="",
    )
    text = packet.to_prompt_text(max_chars=200)
    assert len(text) <= 220
    assert "... [truncated]" in text


def test_compact_structured_parses_exception():
    packet = EvidenceCompactor.compact_structured(
        SAMPLE_TRACEBACK,
        raw_artifact_ref="ref.json",
        repro_command="pytest tests/test_foo.py::test_baz",
    )
    assert packet.exception_type == "AssertionError"
    assert "assert 1 == 2" in packet.exception_message
    assert packet.top_failing_file == "tests/test_foo.py"
    assert packet.top_failing_line == 42
    assert packet.raw_artifact_ref == "ref.json"


def test_compact_structured_large_traceback_omits_bytes():
    packet = EvidenceCompactor.compact_structured(
        LARGE_TRACEBACK,
        max_chars=2000,
    )
    assert packet.omitted_bytes > 0
    prompt = packet.to_prompt_text(max_chars=2000)
    assert "[OMITTED]" in prompt
    assert "bytes suppressed" in prompt


def test_compact_structured_empty_evidence():
    packet = EvidenceCompactor.compact_structured("")
    assert packet.exception_type == "UnknownError"
    assert packet.omitted_bytes == 0


def test_compact_structured_env_failure_reason():
    packet = EvidenceCompactor.compact_structured(
        SAMPLE_TRACEBACK,
        env_failure_reason="Ollama model not available",
    )
    prompt = packet.to_prompt_text()
    assert "[ENV_FAILURE] Ollama model not available" in prompt


def test_compact_structured_preserves_raw_ref():
    packet = EvidenceCompactor.compact_structured(
        SAMPLE_TRACEBACK,
        raw_artifact_ref="artifacts/run_001.json",
    )
    assert packet.raw_artifact_ref == "artifacts/run_001.json"
    prompt = packet.to_prompt_text()
    assert "run_001.json" in prompt


def test_compact_still_works():
    result = EvidenceCompactor.compact(SAMPLE_TRACEBACK, limit=200)
    assert "AssertionError" in result or "assert" in result
    assert len(result) <= 220


def test_compact_small_evidence_unchanged():
    result = EvidenceCompactor.compact("short text", limit=3000)
    assert result == "short text"
