import pytest
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.evidence_compactor import StructuredPacket
from nexus.services.local_heal.corrector import SelfCorrector


def test_structured_packet_to_prompt_text_used():
    """Verify that StructuredPacket.to_prompt_text() output is embedded in the retry prompt."""
    sp = StructuredPacket(
        exception_type="ZeroDivisionError",
        exception_message="division by zero",
        top_failing_file="math.py",
        top_failing_line=10,
        repro_command="pytest math_test.py",
        relevant_source_span="def div():\n    return 1 / 0",
        env_failure_reason="",
        omitted_bytes=100,
        raw_artifact_ref="verification_report.txt"
    )
    
    error = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message="ZeroDivisionError: division by zero")
    corrector = SelfCorrector()
    
    prompt = corrector.build_retry_prompt(
        original_user_prompt="fix division",
        error=error,
        targeted_files="math.py",
        structured_packet=sp
    )
    
    # 檢查 to_prompt_text() 生成的 key block 確實有被使用
    assert "[EXCEPTION] ZeroDivisionError: division by zero" in prompt
    assert "[LOCATION] math.py:10" in prompt
    assert "[REPRO] pytest math_test.py" in prompt
    assert "[SOURCE]" in prompt
    assert "[OMITTED] 100 bytes suppressed" in prompt
    assert "[RAW_REF] verification_report.txt" in prompt


def test_retry_prompt_contains_compacted_failure():
    """Ensure retry prompt contains exception type and location and not raw logs."""
    sp = StructuredPacket(
        exception_type="AssertionError",
        exception_message="assert False",
        top_failing_file="test_logic.py",
        top_failing_line=45,
        repro_command="pytest test_logic.py",
        relevant_source_span="",
        env_failure_reason="env_interpreter_mismatch",
        omitted_bytes=0,
        raw_artifact_ref=""
    )
    error = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message="AssertionError")
    corrector = SelfCorrector()
    
    prompt = corrector.build_retry_prompt(
        original_user_prompt="fix test",
        error=error,
        targeted_files="test_logic.py",
        structured_packet=sp
    )
    
    assert "[EXCEPTION] AssertionError" in prompt
    assert "[LOCATION] test_logic.py:45" in prompt
    assert "[ENV_FAILURE] env_interpreter_mismatch" in prompt
    # 原始全量日誌不應直接渲染為 primary payload
    assert "Traceback (most recent call last):" not in prompt


def test_raw_log_not_primary_retry_payload():
    """Verify raw logs are compact/omitted and not the primary payload in prompt."""
    sp = StructuredPacket(
        exception_type="NameError",
        exception_message="name 'x' is not defined",
        top_failing_file="app.py",
        top_failing_line=12,
        repro_command="python app.py",
        relevant_source_span="x = y + 1",
        env_failure_reason="",
        omitted_bytes=500,
        raw_artifact_ref="logs.txt"
    )
    error = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message="Traceback...")
    corrector = SelfCorrector()
    
    prompt = corrector.build_retry_prompt(
        original_user_prompt="fix syntax",
        error=error,
        targeted_files="app.py",
        structured_packet=sp
    )
    
    assert "[OMITTED] 500 bytes suppressed" in prompt
    assert "[RAW_REF] logs.txt" in prompt
    assert "Traceback..." not in prompt # check raw log is suppressed


def test_env_failure_classification_propagated():
    """Verify env_failure_reason is propagated into prompt when present."""
    sp = StructuredPacket(
        exception_type="ImportError",
        exception_message="no module named django",
        top_failing_file="manage.py",
        top_failing_line=5,
        repro_command="python manage.py runserver",
        relevant_source_span="",
        env_failure_reason="environment_bootstrap_interpreter_mismatch",
        omitted_bytes=0,
        raw_artifact_ref=""
    )
    error = PatchError(kind=PatchErrorKind.LOGIC_REGRESSION, message="ImportError")
    corrector = SelfCorrector()
    
    prompt = corrector.build_retry_prompt(
        original_user_prompt="fix django import",
        error=error,
        targeted_files="manage.py",
        structured_packet=sp
    )
    
    assert "[ENV_FAILURE] environment_bootstrap_interpreter_mismatch" in prompt
